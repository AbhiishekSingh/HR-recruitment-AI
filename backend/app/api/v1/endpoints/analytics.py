from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.api.deps import get_db, get_current_user
from app.models.assessment import Assessment
from app.models.job_posting import JobPosting
from app.models.company import Company
from app.models.user import User

router = APIRouter()


@router.get("/funnel")
async def hiring_funnel(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    total = (await db.execute(select(func.count(Assessment.id)))).scalar()
    shortlisted = (await db.execute(select(func.count(Assessment.id)).where(Assessment.final_status == "Share to Client"))).scalar()
    sent = (await db.execute(select(func.count(Assessment.id)).where(Assessment.sent_to_client == True))).scalar()
    interested = (await db.execute(select(func.count(Assessment.id)).where(Assessment.client_feedback == "Interested"))).scalar()

    return {
        "Resumes received": total,
        "Shortlisted": shortlisted,
        "Sent to Client": sent,
        "Interested": interested,
    }


@router.get("/by-role")
async def per_role_breakdown(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    jobs_result = await db.execute(select(JobPosting))
    jobs = jobs_result.scalars().all()

    rows = []
    for job in jobs:
        company = await db.get(Company, job.company_id)
        assessments_result = await db.execute(select(Assessment).where(Assessment.job_id == job.id))
        assessments = assessments_result.scalars().all()

        rows.append({
            "job_id": str(job.id),
            "title": job.title,
            "company": company.name if company else "—",
            "total": len(assessments),
            "pending": sum(1 for a in assessments if not a.screened),
            "screened": sum(1 for a in assessments if a.screened),
        })
    return rows


@router.get("/by-recruiter")
async def recruiter_activity(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Assessment).where(Assessment.screened == True))
    assessments = result.scalars().all()

    by_recruiter: dict[str, dict] = {}
    for a in assessments:
        key = str(a.recruiter_id) if a.recruiter_id else "unknown"
        entry = by_recruiter.setdefault(key, {"screened": 0, "shortlisted": 0})
        entry["screened"] += 1
        if a.final_status == "Share to Client":
            entry["shortlisted"] += 1

    return [{"recruiter_id": k, **v} for k, v in by_recruiter.items()]
