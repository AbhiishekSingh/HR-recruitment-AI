import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.api.deps import get_db, get_current_user
from app.models.assessment import Assessment
from app.models.candidate import Candidate
from app.models.job_posting import JobPosting
from app.models.user import User
from app.schemas.assessment import AssessmentCreate, AssessmentScored, ClientFeedbackUpdate
from app.services.scoring.placeholder_engine import compute_final_score

router = APIRouter()


def _to_scored(assessment: Assessment, candidate: Candidate, job: JobPosting) -> dict:
    result = compute_final_score(job, candidate, assessment)
    return {
        **{c.name: getattr(assessment, c.name) for c in assessment.__table__.columns},
        # Carried over from the related Candidate row (already loaded by the
        # caller) so the frontend gets a display-ready row in one response.
        "candidate_name": candidate.name,
        "candidate_email": candidate.email,
        "candidate_experience_years": candidate.experience_years,
        "candidate_current_company": candidate.current_company,
        "ai_score": result["ai"]["score"],
        "matched_skills": result["ai"]["matched_skills"],
        "missing_skills": result["ai"]["missing_skills"],
        "assessment_score": result["assessment"]["score"] if result["assessment"] else None,
        "final_score": result["final"],
        "bucket": result["bucket"],
        "flags": result["flags"],
        "adjustments": result["adjustments"],
    }


@router.get("/jobs/{job_id}/pipeline", response_model=list[AssessmentScored])
async def get_job_pipeline(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The per-job candidate pool — every assessment for this job, scored.
    Matches the prototype's 'Candidate Pipeline' view for one JD."""
    job = await db.get(JobPosting, job_id)
    if not job:
        raise HTTPException(404, "Job posting not found")

    result = await db.execute(select(Assessment).where(Assessment.job_id == job_id))
    assessments = result.scalars().all()

    # Batch-fetch every candidate this pipeline needs in one query instead of
    # one `db.get()` per row (was N+1 — 50 assessments meant 51 round trips).
    candidate_ids = {a.candidate_id for a in assessments}
    candidates_by_id: dict[uuid.UUID, Candidate] = {}
    if candidate_ids:
        cand_result = await db.execute(select(Candidate).where(Candidate.id.in_(candidate_ids)))
        candidates_by_id = {c.id: c for c in cand_result.scalars().all()}

    scored = []
    for a in assessments:
        candidate = candidates_by_id.get(a.candidate_id)
        if candidate:
            scored.append(_to_scored(a, candidate, job))

    # Pending rows first (nothing waiting on screening gets buried), then by final score desc.
    scored.sort(key=lambda s: (0 if s["bucket"] == "pending" else 1, -(s["final_score"] or 0)))
    return scored


@router.get("/candidates/{candidate_id}/assessments", response_model=list[AssessmentScored])
async def get_candidate_assessments(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """All of one candidate's applications/screenings across every job — the
    candidate profile's 'Applications & assessments' view."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    result = await db.execute(select(Assessment).where(Assessment.candidate_id == candidate_id))
    assessments = result.scalars().all()

    scored = []
    for a in assessments:
        job = await db.get(JobPosting, a.job_id)
        if job:
            scored.append(_to_scored(a, candidate, job))
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

    return _to_scored(assessment, candidate, job)


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

    await db.commit()
    await db.refresh(assessment)

    candidate = await db.get(Candidate, assessment.candidate_id)
    job = await db.get(JobPosting, assessment.job_id)
    return _to_scored(assessment, candidate, job)


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
    await db.commit()
    await db.refresh(assessment)

    candidate = await db.get(Candidate, assessment.candidate_id)
    job = await db.get(JobPosting, assessment.job_id)
    return _to_scored(assessment, candidate, job)


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
    return _to_scored(assessment, candidate, job)