import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyCreate, CompanyOut

router = APIRouter()


@router.post("", response_model=CompanyOut)
async def create_company(
    payload: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = Company(**payload.model_dump())
    db.add(company)
    await db.commit()
    await db.refresh(company)
    return company


@router.get("", response_model=list[CompanyOut])
async def list_companies(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Company).where(Company.deleted_at.is_(None)).order_by(Company.onboarded_on.desc())
    )
    return result.scalars().all()


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    company = await db.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise HTTPException(404, "Company not found")
    return company


@router.delete("/{company_id}", status_code=204)
async def delete_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Soft delete only — a company row is the anchor for its jobs, and jobs
    are the anchor for match_results/assessments, so a hard delete would
    either cascade-destroy the agency's whole history for that client or
    orphan foreign keys. deleted_at hides it from list/get; nothing else
    changes, so historical jobs/assessments tied to it stay intact."""
    company = await db.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise HTTPException(404, "Company not found")
    company.deleted_at = datetime.now(timezone.utc)
    await db.commit()
