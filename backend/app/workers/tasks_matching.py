import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.services.llm.factory import get_llm_provider
from app.services.embeddings.factory import get_embedding_provider
from app.services.search.hybrid_search import hybrid_search
from app.models.job_posting import JobPosting
from app.models.candidate_profile import CandidateProfile
from app.models.match_result import MatchResult


@celery_app.task(bind=True, max_retries=3)
def run_matching_task(self, job_id: str, top_k: int | None = None):
    """Runs the matching pipeline for one JD against the full resume pool.
    See project doc, Section 4.2."""
    try:
        asyncio.run(_run_matching(job_id, top_k))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


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

        # 3. Hybrid search across the full resume pool -> top-K candidates
        keywords = " ".join(
            job.requirements.get("required_skills", []) + job.requirements.get("hard_requirements", [])
        )
        candidates = await hybrid_search(db, job.embedding, keywords, top_k)

        # 4. Fetch full profiles + 5. GPT-5 scoring pass, per candidate
        for c in candidates:
            profile = await db.get(CandidateProfile, c["candidate_id"])
            if not profile:
                continue

            candidate_profile_dict = {
                "skills": profile.skills,
                "work_history": profile.work_history,
                "education": profile.education,
                "certifications": profile.certifications,
                "total_experience_years": profile.total_experience_years,
            }
            result = await llm.score_candidate(job.requirements, candidate_profile_dict)

            match = MatchResult(
                job_id=job.id,
                candidate_id=c["candidate_id"],
                score=result.get("score", 0),
                matched_skills=result.get("matched_skills", []),
                missing_skills=result.get("missing_skills", []),
                strengths=result.get("strengths", []),
                gaps=result.get("gaps", []),
                recommendation=result.get("recommendation", "Review"),
                model_version=llm.model,
            )
            db.add(match)
        await db.commit()


def _build_jd_summary(requirements: dict) -> str:
    req = ", ".join(requirements.get("required_skills", []))
    resp = "; ".join(requirements.get("responsibilities", []))
    return f"Required skills: {req}\nResponsibilities: {resp}"
