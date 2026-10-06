from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

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
    selected = (await db.execute(select(func.count(Assessment.id)).where(Assessment.stage.in_(["Selected", "Joined"])))).scalar()
    joined = (await db.execute(select(func.count(Assessment.id)).where(Assessment.stage == "Joined"))).scalar()
    invoiced = (await db.execute(select(func.count(Assessment.id)).where(Assessment.stage == "Joined", Assessment.invoice_raised == True))).scalar()

    return {
        "Resumes received": total,
        "Shortlisted": shortlisted,
        "Sent to Client": sent,
        "Interested": interested,
        "Selected": selected,
        "Joined": joined,
        "Invoice raised": invoiced,
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


TASK_LABELS = {
    "resume_extraction": "Resume reading",
    "resume_vision": "Scanned resume reading",
    "resume_transcription": "Scanned resume text copy",
    "jd_reading": "JD file reading",
    "jd_requirements": "JD requirements",
    "candidate_scoring": "AI candidate scoring",
    "embedding": "Embeddings (search vectors)",
}


@router.get("/ai-usage")
async def ai_usage_report(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exact AI spend from ai_usage_log (one row per API call)."""
    from datetime import datetime, timedelta, timezone
    from app.config import settings
    from app.models.ai_usage_log import AIUsageLog

    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rate = settings.usd_to_inr
    window = AIUsageLog.created_at >= since

    totals = (await db.execute(
        select(func.count(AIUsageLog.id), func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
               func.coalesce(func.sum(case((AIUsageLog.priced == False, 1), else_=0)), 0))  # noqa: E712
        .where(window)
    )).one()

    by_task_rows = (await db.execute(
        select(AIUsageLog.task, func.count(AIUsageLog.id), func.sum(AIUsageLog.cost_usd),
               func.sum(AIUsageLog.input_tokens), func.sum(AIUsageLog.output_tokens))
        .where(window).group_by(AIUsageLog.task).order_by(func.sum(AIUsageLog.cost_usd).desc())
    )).all()

    by_job_rows = (await db.execute(
        select(AIUsageLog.job_id, JobPosting.title, Company.name, func.count(AIUsageLog.id), func.sum(AIUsageLog.cost_usd))
        .join(JobPosting, JobPosting.id == AIUsageLog.job_id)
        .outerjoin(Company, Company.id == JobPosting.company_id)
        .where(window, AIUsageLog.job_id.is_not(None))
        .group_by(AIUsageLog.job_id, JobPosting.title, Company.name)
        .order_by(func.sum(AIUsageLog.cost_usd).desc())
        .limit(10)
    )).all()

    day_col = func.date(AIUsageLog.created_at)
    by_day_rows = (await db.execute(
        select(day_col, func.sum(AIUsageLog.cost_usd)).where(window).group_by(day_col).order_by(day_col)
    )).all()

    return {
        "days": days,
        "usd_to_inr": rate,
        "calls": totals[0],
        "unpriced_calls": int(totals[2] or 0),
        "total_usd": round(float(totals[1] or 0), 4),
        "total_inr": round(float(totals[1] or 0) * rate, 2),
        "by_task": [
            {"task": t, "label": TASK_LABELS.get(t, t), "calls": n,
             "cost_usd": round(float(c or 0), 4), "cost_inr": round(float(c or 0) * rate, 2),
             "input_tokens": int(i or 0), "output_tokens": int(o or 0)}
            for t, n, c, i, o in by_task_rows
        ],
        "by_job": [
            {"job_id": str(j), "title": title, "company": company or "—", "calls": n,
             "cost_inr": round(float(c or 0) * rate, 2)}
            for j, title, company, n, c in by_job_rows
        ],
        "by_day": [{"date": str(d), "cost_inr": round(float(c or 0) * rate, 2)} for d, c in by_day_rows],
    }
