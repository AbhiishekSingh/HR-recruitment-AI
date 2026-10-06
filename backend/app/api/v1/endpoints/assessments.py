import uuid

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.config import settings
from app.models.ai_usage_log import AIUsageLog
from app.models.candidate_embedding import CandidateEmbedding
from app.services import ai_usage
from app.services.scoring.job_config import effective_config
from app.workers.tasks_matching import ai_score_candidates_task

from app.api.deps import get_db, get_current_user
from app.models.assessment import Assessment
from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.job_posting import JobPosting
from app.models.match_result import MatchResult
from app.models.user import User
from app.schemas.assessment import AssessmentCreate, AssessmentScored, ClientFeedbackUpdate
from app.services.scoring.placeholder_engine import compute_final_score
from app.services.tracking.stages import change_stage, sync_stage_from_screening

router = APIRouter()


async def _get_match_result(db: AsyncSession, job_id: uuid.UUID, candidate_id: uuid.UUID) -> MatchResult | None:
    result = await db.execute(
        select(MatchResult).where(MatchResult.job_id == job_id, MatchResult.candidate_id == candidate_id)
    )
    return result.scalar_one_or_none()


# Jobs whose "meaning match" embedding has already been queued by this
# process, so a pipeline page polling every few seconds doesn't queue it
# again and again while the worker is still building it.
_embedding_requested: set[uuid.UUID] = set()


def _ensure_job_embedding(job: JobPosting) -> None:
    if job.embedding is not None or job.id in _embedding_requested:
        return
    _embedding_requested.add(job.id)
    try:
        from app.workers.tasks_matching import embed_job_task
        embed_job_task.delay(str(job.id))
    except Exception:
        _embedding_requested.discard(job.id)


async def _similarities(db: AsyncSession, job: JobPosting, candidate_ids) -> dict[uuid.UUID, float]:
    """JD-vs-resume cosine similarity for the "meaning match" part of the
    smart score. Uses embeddings that already exist -- no AI call."""
    ids = list(candidate_ids)
    if not ids:
        return {}
    if job.embedding is None:
        _ensure_job_embedding(job)
        return {}
    distance = CandidateEmbedding.embedding.cosine_distance(job.embedding)
    rows = await db.execute(
        select(CandidateEmbedding.candidate_id, distance).where(CandidateEmbedding.candidate_id.in_(ids))
    )
    return {cid: 1 - float(d) for cid, d in rows.all() if d is not None}


def _to_scored(
    assessment: Assessment,
    candidate: Candidate,
    job: JobPosting,
    match_result: MatchResult | None = None,
    candidate_profile: CandidateProfile | None = None,
    config: dict | None = None,
    similarity: float | None = None,
) -> dict:
    result = compute_final_score(job, candidate, assessment, match_result, candidate_profile, config, similarity)
    ai = result["ai"]
    smart = result["smart"]
    return {
        **{c.name: getattr(assessment, c.name) for c in assessment.__table__.columns},
        # Carried over from the related Candidate row (already loaded by the
        # caller) so the frontend gets a display-ready row in one response.
        "candidate_name": candidate.name,
        "candidate_email": candidate.email,
        "candidate_experience_years": candidate.experience_years,
        "candidate_current_company": candidate.current_company,
        "candidate_status": candidate.status,
        "ai_score": ai["score"],
        "ai_source": ai.get("source"),
        "matched_skills": ai["matched_skills"],
        "missing_skills": ai["missing_skills"],
        "smart_score": smart["score"],
        "score_parts": smart["parts"],
        "skill_evidence": smart["evidence"],
        "ai_stale": result["ai_stale"],
        "ai_previous_score": result["ai_previous_score"],
        "ai_strengths": ai.get("strengths", []) if ai.get("source") == "ai_pipeline" else [],
        "ai_gaps": ai.get("gaps", []) if ai.get("source") == "ai_pipeline" else [],
        "ai_recommendation": ai.get("recommendation") if ai.get("source") == "ai_pipeline" else None,
        "assessment_score": result["assessment"]["score"] if result["assessment"] else None,
        "final_score": result["final"],
        "bucket": result["bucket"],
        "flags": result["flags"],
        "adjustments": result["adjustments"],
    }


async def _score_single(db, assessment, candidate, job, match_result, candidate_profile) -> dict:
    sims = await _similarities(db, job, [candidate.id])
    return _to_scored(assessment, candidate, job, match_result, candidate_profile,
                      effective_config(job), sims.get(candidate.id))


async def _pipeline_rows(db: AsyncSession, job: JobPosting) -> list[dict]:
    """Every assessment for this job, scored and sorted (shared by the
    pipeline view and the AI-scoring selection, so "top 20" means exactly
    the top 20 HR sees)."""
    result = await db.execute(select(Assessment).where(Assessment.job_id == job.id))
    assessments = result.scalars().all()

    # Batch-fetch everything in one query per table (no N+1).
    candidate_ids = {a.candidate_id for a in assessments}
    candidates_by_id: dict[uuid.UUID, Candidate] = {}
    match_results_by_candidate: dict[uuid.UUID, MatchResult] = {}
    profiles_by_candidate: dict[uuid.UUID, CandidateProfile] = {}
    if candidate_ids:
        cand_result = await db.execute(select(Candidate).where(Candidate.id.in_(candidate_ids)))
        candidates_by_id = {c.id: c for c in cand_result.scalars().all()}
        mr_result = await db.execute(
            select(MatchResult).where(MatchResult.job_id == job.id, MatchResult.candidate_id.in_(candidate_ids))
        )
        match_results_by_candidate = {mr.candidate_id: mr for mr in mr_result.scalars().all()}
        profile_result = await db.execute(
            select(CandidateProfile).where(CandidateProfile.candidate_id.in_(candidate_ids))
        )
        profiles_by_candidate = {p.candidate_id: p for p in profile_result.scalars().all()}

    config = effective_config(job)
    sims = await _similarities(db, job, candidate_ids)

    scored = []
    for a in assessments:
        candidate = candidates_by_id.get(a.candidate_id)
        if candidate and candidate.deleted_at is None:
            scored.append(_to_scored(
                a, candidate, job,
                match_results_by_candidate.get(a.candidate_id),
                profiles_by_candidate.get(a.candidate_id),
                config, sims.get(a.candidate_id),
            ))

    # Pending rows first (nothing waiting on screening gets buried), each
    # group ordered best first: pending by their (smart or AI) score,
    # screened by final score.
    scored.sort(key=lambda s: (
        0 if s["bucket"] == "pending" else 1,
        -((s["ai_score"] if s["bucket"] == "pending" else s["final_score"]) or 0),
    ))
    return scored


@router.get("/jobs/{job_id}/pipeline", response_model=list[AssessmentScored])
async def get_job_pipeline(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The per-job candidate pool — every assessment for this job, scored.
    Matches the prototype's 'Candidate Pipeline' view for one JD."""
    job = await db.get(JobPosting, job_id)
    if not job:
        raise HTTPException(404, "Job posting not found")
    return await _pipeline_rows(db, job)


class AIScoreRequest(BaseModel):
    # top = best N by score; above = score >= min_score; selected = these
    # candidates; stale = every out-of-date AI score
    mode: Literal["top", "above", "selected", "stale"] = "top"
    count: int = Field(20, ge=1, le=200)
    min_score: int = Field(70, ge=0, le=100)
    candidate_ids: list[uuid.UUID] = []
    dry_run: bool = True


class AIScoreResponse(BaseModel):
    to_score: int
    already_done: int
    not_ready: int
    candidate_ids: list[uuid.UUID]
    cost_per_candidate_inr: float
    estimated_cost_inr: float
    estimated_cost_usd: float
    queued: bool = False


async def _avg_scoring_cost_usd(db: AsyncSession) -> float:
    """Average real cost of recent AI scoring calls (falls back to the
    estimate until there are some)."""
    rows = (await db.execute(
        select(AIUsageLog.cost_usd)
        .where(AIUsageLog.task == "candidate_scoring", AIUsageLog.priced == True)  # noqa: E712
        .order_by(AIUsageLog.created_at.desc())
        .limit(50)
    )).scalars().all()
    return (sum(rows) / len(rows)) if len(rows) >= 5 else ai_usage.DEFAULT_SCORING_COST_USD


@router.post("/jobs/{job_id}/ai-score", response_model=AIScoreResponse)
async def ai_score_candidates(
    job_id: uuid.UUID,
    payload: AIScoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """On-demand AI scoring. With dry_run=true (the default) nothing is
    spent: it returns how many candidates would be scored and the estimated
    cost, for the confirm dialog. Candidates whose AI score is already up
    to date are skipped (no double charge); candidates whose resume isn't
    processed yet can't be AI-scored."""
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")

    rows = await _pipeline_rows(db, job)
    if payload.mode == "top":
        ranked = sorted(rows, key=lambda r: -(r["smart_score"] or 0))
        chosen = ranked[: payload.count]
    elif payload.mode == "above":
        chosen = [r for r in rows if (r["smart_score"] or 0) >= payload.min_score]
    elif payload.mode == "stale":
        chosen = [r for r in rows if r["ai_stale"]]
    else:
        wanted = set(payload.candidate_ids)
        chosen = [r for r in rows if r["candidate_id"] in wanted]

    already = [r for r in chosen if r["ai_source"] == "ai_pipeline"]
    not_ready = [r for r in chosen if r["ai_source"] != "ai_pipeline" and r["candidate_status"] != "ready"]
    to_score = [r for r in chosen if r["ai_source"] != "ai_pipeline" and r["candidate_status"] == "ready"]
    ids = [r["candidate_id"] for r in to_score]

    per_usd = await _avg_scoring_cost_usd(db)
    response = AIScoreResponse(
        to_score=len(ids), already_done=len(already), not_ready=len(not_ready), candidate_ids=ids,
        cost_per_candidate_inr=round(per_usd * settings.usd_to_inr, 2),
        estimated_cost_inr=round(per_usd * len(ids) * settings.usd_to_inr, 2),
        estimated_cost_usd=round(per_usd * len(ids), 4),
    )
    if payload.dry_run or not ids:
        return response
    try:
        ai_score_candidates_task.delay(str(job.id), [str(i) for i in ids])
    except Exception:
        raise HTTPException(503, "Could not start AI scoring: the background worker (Celery/Redis) is not reachable")
    response.queued = True
    return response


@router.get("/candidates/{candidate_id}/assessments", response_model=list[AssessmentScored])
async def get_candidate_assessments(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """All of one candidate's applications/screenings across every job — the
    candidate profile's 'Applications & assessments' view."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    result = await db.execute(select(Assessment).where(Assessment.candidate_id == candidate_id))
    assessments = result.scalars().all()

    # Same candidate across every row here, so one profile fetch covers all
    # of them (unlike match_result, which varies per job).
    candidate_profile = await db.get(CandidateProfile, candidate_id)

    scored = []
    for a in assessments:
        job = await db.get(JobPosting, a.job_id)
        if job:
            match_result = await _get_match_result(db, a.job_id, candidate_id)
            scored.append(await _score_single(db, a, candidate, job, match_result, candidate_profile))
    return scored


class AssessOneRequest(BaseModel):
    candidate_id: uuid.UUID
    job_id: uuid.UUID


@router.post("/assessments/start", response_model=AssessmentScored)
async def start_or_get_assessment(
    payload: AssessOneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """'Assess one candidate for this role' — returns the existing assessment
    (pending or screened) if one already exists for this pair, or creates a
    fresh Pending Screening stub otherwise. The frontend's screening form
    always PATCHes this row afterward, whichever path created it."""
    candidate = await db.get(Candidate, payload.candidate_id)
    job = await db.get(JobPosting, payload.job_id)
    if not candidate or not job:
        raise HTTPException(404, "Candidate or job not found")

    result = await db.execute(
        select(Assessment).where(Assessment.candidate_id == payload.candidate_id, Assessment.job_id == payload.job_id)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        assessment = Assessment(candidate_id=payload.candidate_id, job_id=payload.job_id,
                                 final_status="Pending Screening", screened=False)
        db.add(assessment)
        await db.commit()
        await db.refresh(assessment)

    match_result = await _get_match_result(db, payload.job_id, payload.candidate_id)
    candidate_profile = await db.get(CandidateProfile, payload.candidate_id)
    return await _score_single(db, assessment, candidate, job, match_result, candidate_profile)


@router.patch("/assessments/{assessment_id}", response_model=AssessmentScored)
async def submit_screening(
    assessment_id: uuid.UUID,
    payload: AssessmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Completes a Pending Screening stub, or edits an already-screened
    record — same endpoint handles both, matching the prototype's single
    screening-call form used for either case."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")

    for field, value in payload.model_dump().items():
        setattr(assessment, field, value)
    assessment.screened = True
    assessment.recruiter_id = current_user.id
    sync_stage_from_screening(db, assessment, current_user.id)

    await db.commit()
    await db.refresh(assessment)

    candidate = await db.get(Candidate, assessment.candidate_id)
    job = await db.get(JobPosting, assessment.job_id)
    match_result = await _get_match_result(db, assessment.job_id, assessment.candidate_id)
    candidate_profile = await db.get(CandidateProfile, assessment.candidate_id)
    return await _score_single(db, assessment, candidate, job, match_result, candidate_profile)


class StatusUpdate(BaseModel):
    status: str  # "Share to Client" | "Hold" | "Reject"


@router.post("/assessments/{assessment_id}/status", response_model=AssessmentScored)
async def set_status(
    assessment_id: uuid.UUID,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    assessment.final_status = payload.status
    sync_stage_from_screening(db, assessment, current_user.id)
    await db.commit()
    await db.refresh(assessment)

    candidate = await db.get(Candidate, assessment.candidate_id)
    job = await db.get(JobPosting, assessment.job_id)
    match_result = await _get_match_result(db, assessment.job_id, assessment.candidate_id)
    candidate_profile = await db.get(CandidateProfile, assessment.candidate_id)
    return await _score_single(db, assessment, candidate, job, match_result, candidate_profile)


class SendToClientRequest(BaseModel):
    assessment_ids: list[uuid.UUID]


@router.post("/assessments/send-to-client")
async def send_to_client(
    payload: SendToClientRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = 0
    for aid in payload.assessment_ids:
        assessment = await db.get(Assessment, aid)
        if assessment:
            assessment.sent_to_client = True
            # Moves Shortlisted -> Submitted (and stamps submitted_on); never
            # moves a candidate who is already further along backwards.
            if (assessment.stage or "") in ("", "Shortlisted"):
                change_stage(db, assessment, "Submitted", current_user.id, "Sent to client")
            count += 1
    await db.commit()
    return {"sent": count}


@router.post("/assessments/{assessment_id}/client-feedback", response_model=AssessmentScored)
async def client_feedback(
    assessment_id: uuid.UUID,
    payload: ClientFeedbackUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """No separate client auth yet — the client portal is agency-staff-viewed
    for now (matching the prototype's 'simulated' client portal). Real
    client-facing auth is a later addition, not part of this foundation."""
    assessment = await db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    assessment.client_feedback = payload.feedback
    await db.commit()
    await db.refresh(assessment)

    candidate = await db.get(Candidate, assessment.candidate_id)
    job = await db.get(JobPosting, assessment.job_id)
    match_result = await _get_match_result(db, assessment.job_id, assessment.candidate_id)
    candidate_profile = await db.get(CandidateProfile, assessment.candidate_id)
    return await _score_single(db, assessment, candidate, job, match_result, candidate_profile)