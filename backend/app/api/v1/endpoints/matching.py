import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.candidate import Candidate
from app.models.job_posting import JobPosting
from app.models.match_result import MatchResult
from app.models.user import User
from app.schemas.match import MatchResultOut, MatchRunRequest
from app.workers.tasks_matching import run_matching_task

router = APIRouter()


@router.post("/{job_id}/match")
async def trigger_matching(
    job_id: uuid.UUID,
    payload: MatchRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")

    task = run_matching_task.delay(str(job_id), payload.top_k)
    return {"task_id": task.id, "status": "queued"}


@router.get("/{job_id}/shortlist", response_model=list[MatchResultOut])
async def get_shortlist(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Was missing get_current_user entirely — every other endpoint in this
    # router requires auth, this one didn't, so match/candidate data for any
    # job was reachable unauthenticated given just the job_id.
    # Also excludes candidates soft-deleted since they were last scored,
    # matching the same deleted_at convention as every list/get endpoint.
    result = await db.execute(
        select(MatchResult)
        .join(Candidate, Candidate.id == MatchResult.candidate_id)
        .where(MatchResult.job_id == job_id, Candidate.deleted_at.is_(None))
        .order_by(MatchResult.score.desc())
    )
    return result.scalars().all()
