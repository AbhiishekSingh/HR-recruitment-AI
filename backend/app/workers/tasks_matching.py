import asyncio
import hashlib
import json
import uuid

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.workers.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.config import settings
from app.services.llm.factory import get_llm_provider
from app.services.embeddings.factory import get_embedding_provider
from app.services.search.hybrid_search import hybrid_search
from app.models.job_posting import JobPosting
from app.models.candidate_profile import CandidateProfile
from app.models.match_result import MatchResult

# Caps how many GPT-5 scoring calls run at once per job. Keeps a 500-candidate
# job from firing 500 simultaneous requests (rate limits, cost spikes) while
# still scoring in parallel instead of one-by-one.
MAX_CONCURRENT_SCORING_CALLS = 5


@celery_app.task(bind=True, max_retries=3)
def run_matching_task(self, job_id: str, top_k: int | None = None):
    """Runs the matching pipeline for one JD against the full resume pool.
    See project doc, Section 4.2."""
    try:
        asyncio.run(_run_matching(job_id, top_k))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


def _compute_requirements_hash(requirements: dict, extraction_model_version: str) -> str:
    """Identifies a (job requirements, resume extraction) pair. Unchanged on a
    re-match => the existing MatchResult is still valid and the LLM call is
    skipped entirely. Changes the moment the JD is edited (job.requirements
    changes) or the resume is re-extracted (extraction_model_version changes),
    so a stale score can never be silently reused."""
    payload = json.dumps(
        {"requirements": requirements, "extraction_model_version": extraction_model_version},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _upsert_match_result(db, *, job_id, candidate_id, score_result, requirements_hash, model_version):
    """INSERT ... ON CONFLICT (job_id, candidate_id) DO UPDATE, relying on the
    uq_match_results_job_candidate constraint. A plain db.add() would raise a
    unique-violation the second time a job is matched, since a MatchResult row
    for that pair already exists after the first run."""
    stmt = pg_insert(MatchResult).values(
        id=uuid.uuid4(),
        job_id=job_id,
        candidate_id=candidate_id,
        score=score_result.get("score", 0),
        matched_skills=score_result.get("matched_skills", []),
        missing_skills=score_result.get("missing_skills", []),
        strengths=score_result.get("strengths", []),
        gaps=score_result.get("gaps", []),
        recommendation=score_result.get("recommendation", "Review"),
        requirements_hash=requirements_hash,
        model_version=model_version,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_match_results_job_candidate",
        set_={
            "score": stmt.excluded.score,
            "matched_skills": stmt.excluded.matched_skills,
            "missing_skills": stmt.excluded.missing_skills,
            "strengths": stmt.excluded.strengths,
            "gaps": stmt.excluded.gaps,
            "recommendation": stmt.excluded.recommendation,
            "requirements_hash": stmt.excluded.requirements_hash,
            "model_version": stmt.excluded.model_version,
            "scored_at": func.now(),
        },
    )
    await db.execute(stmt)


async def _run_matching(job_id: str, top_k: int | None):
    async with AsyncSessionLocal() as db:
        job = await db.get(JobPosting, uuid.UUID(job_id))
        if not job:
            return

        llm = get_llm_provider()

        # 1. Extract structured JD requirements if not already done
        if not job.requirements:
            job.requirements = await llm.extract_jd(job.raw_text)
            await db.commit()

        # 2. Embed the JD
        embedder = get_embedding_provider()
        if job.embedding is None:
            summary = _build_jd_summary(job.requirements)
            vectors = await embedder.embed([summary])
            job.embedding = vectors[0]
            await db.commit()

        # 3. Hard-requirement SQL pre-filter + hybrid search -> top-K candidates
        keywords = " ".join(
            job.requirements.get("required_skills", []) + job.requirements.get("hard_requirements", [])
        )
        candidates = await hybrid_search(
            db, job.embedding, keywords, top_k,
            experience_min=job.experience_min,
            hard_requirements=job.requirements.get("hard_requirements", []),
        )
        if not candidates:
            return

        # Pull existing MatchResult rows for this job in one query, keyed by
        # candidate_id, so each candidate can be hash-checked without a
        # per-candidate SELECT.
        candidate_ids = [c["candidate_id"] for c in candidates]
        existing_rows = await db.execute(
            select(MatchResult.candidate_id, MatchResult.requirements_hash)
            .where(MatchResult.job_id == job.id, MatchResult.candidate_id.in_(candidate_ids))
        )
        existing_hashes = {row.candidate_id: row.requirements_hash for row in existing_rows}

        # Batch-fetched up front into a plain dict, not looked up one at a
        # time inside score_one() below. A SQLAlchemy AsyncSession is NOT
        # safe for concurrent use -- score_one() runs many at once under
        # asyncio.gather, and a `db.get()` per coroutine on the *same*
        # shared session raised InvalidRequestError ("this session is
        # already in progress") or silently interleaved results the moment
        # two candidates were being scored at once. One bulk SELECT here
        # keeps every DB access on this session sequential; score_one()
        # itself never touches `db`.
        profile_rows = await db.execute(
            select(CandidateProfile).where(CandidateProfile.candidate_id.in_(candidate_ids))
        )
        profiles_by_candidate = {p.candidate_id: p for p in profile_rows.scalars().all()}

        # 4. Score each candidate, skip unchanged pairs, GPT-5 score the rest
        # under a concurrency cap.
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCORING_CALLS)

        async def score_one(candidate_id):
            profile = profiles_by_candidate.get(candidate_id)
            if not profile:
                return None

            req_hash = _compute_requirements_hash(job.requirements, profile.extraction_model_version)
            if existing_hashes.get(candidate_id) == req_hash:
                # Requirements + extraction unchanged since last score for
                # this pair -> the stored MatchResult is still accurate,
                # nothing to do (this is the main cost lever: no LLM call).
                return None

            candidate_profile_dict = {
                "skills": profile.skills,
                "work_history": profile.work_history,
                "education": profile.education,
                "certifications": profile.certifications,
                "total_experience_years": profile.total_experience_years,
            }
            async with semaphore:
                result = await llm.score_candidate(job.requirements, candidate_profile_dict)
            return candidate_id, result, req_hash

        outcomes = await asyncio.gather(*(score_one(cid) for cid in candidate_ids))

        for outcome in outcomes:
            if outcome is None:
                continue
            candidate_id, result, req_hash = outcome
            await _upsert_match_result(
                db,
                job_id=job.id,
                candidate_id=candidate_id,
                score_result=result,
                requirements_hash=req_hash,
                model_version=llm.model,
            )

        await db.commit()


def _build_jd_summary(requirements: dict) -> str:
    req = ", ".join(requirements.get("required_skills", []))
    resp = "; ".join(requirements.get("responsibilities", []))
    return f"Required skills: {req}\nResponsibilities: {resp}"
