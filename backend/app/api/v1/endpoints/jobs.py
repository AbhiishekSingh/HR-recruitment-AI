import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.job_posting import JobPosting
from app.models.company import Company
from app.models.user import User
from app.schemas.job import JobPostingCreate, JobPostingOut

router = APIRouter()


@router.post("", response_model=JobPostingOut)
async def create_job(
    payload: JobPostingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = await db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    job = JobPosting(**payload.model_dump(), created_by=current_user.id, requirements={})
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get("", response_model=list[JobPostingOut])
async def list_jobs(
    company_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(JobPosting).order_by(JobPosting.opened_on.desc())
    if company_id:
        query = query.where(JobPosting.company_id == company_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobPostingOut)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = await db.get(JobPosting, job_id)
    if not job:
        raise HTTPException(404, "Job posting not found")
    return job
