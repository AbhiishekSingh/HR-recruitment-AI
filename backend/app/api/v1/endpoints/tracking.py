"""Post-shortlist recruitment tracking:

  * Shortlisted candidates list (across every job/company)
  * Pipeline stage changes + stage history
  * Submission to client, selection (offered CTC, joining date)
  * Invoice raised YES/NO + date + amount (after joining)
  * Candidate-wise follow-ups / interviews with date, time, status, history
  * Dashboard lists: follow-ups due/overdue, invoice status of hires

All routes are mounted at the API root (prefix="") so they sit next to the
existing /assessments/* routes in assessments.py.
"""
import uuid
from datetime import datetime, timedelta, timezone, date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.assessment import Assessment, PIPELINE_STAGES
from app.models.assessment_stage_history import AssessmentStageHistory
from app.models.candidate import Candidate
from app.models.company import Company
from app.models.follow_up import FollowUp, FOLLOW_UP_TYPES, FOLLOW_UP_STATUSES
from app.models.job_posting import JobPosting
from app.models.user import User
from app.schemas.tracking import (
    TrackingUpdate, StageHistoryOut, FollowUpCreate, FollowUpUpdate, FollowUpOut, ShortlistRow,
)
from app.services.tracking.stages import change_stage, validate_stage

router = APIRouter()

# Stages after which selection details (CTC / joining date) make sense.
SELECTION_STAGES = {"Selected", "Joined", "Offer Declined"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _get_assessment(db: AsyncSession, assessment_id: uuid.UUID) -> Assessment:
    assessment = await db.get(Assessment, assessment_id)
    if not assessment or assessment.deleted_at is not None:
        raise HTTPException(404, "Assessment not found")
    return assessment


async def _user_names(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    result = await db.execute(select(User.id, User.name).where(User.id.in_(ids)))
    return {row.id: row.name for row in result.all()}


async def _labels_for(db: AsyncSession, job_ids: set[uuid.UUID], candidate_ids: set[uuid.UUID]):
    """Batch-fetches the candidate/job/company rows needed to label a list,
    one query per table instead of one per row."""
    candidates: dict[uuid.UUID, Candidate] = {}
    jobs: dict[uuid.UUID, JobPosting] = {}
    companies: dict[uuid.UUID, Company] = {}
    if candidate_ids:
        res = await db.execute(select(Candidate).where(Candidate.id.in_(candidate_ids)))
        candidates = {c.id: c for c in res.scalars().all()}
    if job_ids:
        res = await db.execute(select(JobPosting).where(JobPosting.id.in_(job_ids)))
        jobs = {j.id: j for j in res.scalars().all()}
    company_ids = {j.company_id for j in jobs.values()}
    if company_ids:
        res = await db.execute(select(Company).where(Company.id.in_(company_ids)))
        companies = {c.id: c for c in res.scalars().all()}
    return candidates, jobs, companies


def _follow_up_out(f: FollowUp, candidates, jobs, companies, users) -> dict:
    job = jobs.get(f.job_id)
    company = companies.get(job.company_id) if job else None
    cand = candidates.get(f.candidate_id)
    return {
        "id": f.id,
        "assessment_id": f.assessment_id,
        "candidate_id": f.candidate_id,
        "job_id": f.job_id,
        "follow_up_type": f.follow_up_type,
        "scheduled_at": f.scheduled_at,
        "status": f.status,
        "notes": f.notes,
        "outcome": f.outcome,
        "created_by_name": users.get(f.created_by),
        "created_at": f.created_at,
        "completed_at": f.completed_at,
        "candidate_name": cand.name if cand else "",
        "job_title": job.title if job else "",
        "company_name": company.name if company else "",
    }


async def _grouped_follow_ups(db: AsyncSession, items: list[FollowUp]) -> list[dict]:
    """Collapses reschedule chains into one entry each: the latest row is
    returned, with every earlier date in `previous_schedules` (newest
    first). Rows that were replaced by a reschedule are not returned on
    their own."""
    by_id = {f.id: f for f in items}
    replaced_ids = {f.rescheduled_from_id for f in items if f.rescheduled_from_id}
    heads = [f for f in items if f.id not in replaced_ids]

    candidates, jobs, companies = await _labels_for(
        db, {f.job_id for f in items}, {f.candidate_id for f in items}
    )
    users = await _user_names(db, {f.created_by for f in items})

    out = []
    for head in heads:
        row = _follow_up_out(head, candidates, jobs, companies, users)
        previous = []
        prev_id = head.rescheduled_from_id
        seen = set()
        while prev_id and prev_id in by_id and prev_id not in seen:
            seen.add(prev_id)
            p = by_id[prev_id]
            previous.append({
                "scheduled_at": p.scheduled_at,
                "rescheduled_on": p.completed_at,
                "reason": p.outcome,
                "by_name": users.get(p.created_by),
            })
            prev_id = p.rescheduled_from_id
        row["previous_schedules"] = previous
        out.append(row)
    return out


async def _build_rows(db: AsyncSession, assessments: list[Assessment]) -> list[dict]:
    if not assessments:
        return []
    candidates, jobs, companies = await _labels_for(
        db, {a.job_id for a in assessments}, {a.candidate_id for a in assessments}
    )

    # Next pending follow-up + overdue count per assessment, in one query.
    now = datetime.now(timezone.utc)
    fu_res = await db.execute(
        select(FollowUp)
        .where(
            FollowUp.assessment_id.in_([a.id for a in assessments]),
            FollowUp.status == "Scheduled",
            FollowUp.deleted_at.is_(None),
        )
        .order_by(FollowUp.scheduled_at.asc())
    )
    next_fu: dict[uuid.UUID, FollowUp] = {}
    overdue: dict[uuid.UUID, int] = {}
    for f in fu_res.scalars().all():
        next_fu.setdefault(f.assessment_id, f)
        if f.scheduled_at < now:
            overdue[f.assessment_id] = overdue.get(f.assessment_id, 0) + 1

    rows = []
    for a in assessments:
        cand = candidates.get(a.candidate_id)
        job = jobs.get(a.job_id)
        if not cand or cand.deleted_at is not None or not job:
            continue
        company = companies.get(job.company_id)
        nf = next_fu.get(a.id)
        rows.append({
            "assessment_id": a.id,
            "candidate_id": cand.id,
            "candidate_name": cand.name,
            "candidate_email": cand.email,
            "candidate_phone": cand.phone,
            "job_id": job.id,
            "job_title": job.title,
            "job_status": job.status,
            "company_id": company.id if company else None,
            "company_name": company.name if company else "—",
            "company_active": bool(company.is_active) if company else False,
            "final_status": a.final_status,
            "stage": a.stage or "",
            "submitted_to": a.submitted_to or "",
            "submitted_on": a.submitted_on,
            "current_ctc": a.current_ctc,
            "expected_ctc": a.expected_ctc,
            "offered_ctc": a.offered_ctc,
            "joining_date": a.joining_date,
            "invoice_raised": bool(a.invoice_raised),
            "invoice_date": a.invoice_date,
            "next_follow_up_at": nf.scheduled_at if nf else None,
            "next_follow_up_type": nf.follow_up_type if nf else None,
            "overdue_follow_ups": overdue.get(a.id, 0),
            "updated_at": a.updated_at,
        })
    return rows


# ---------------------------------------------------------------------------
# reference data
# ---------------------------------------------------------------------------

@router.get("/tracking/options")
async def tracking_options(current_user: User = Depends(get_current_user)):
    """Single source of truth for dropdown values used by the frontend."""
    return {
        "stages": PIPELINE_STAGES,
        "follow_up_types": FOLLOW_UP_TYPES,
        "follow_up_statuses": FOLLOW_UP_STATUSES,
    }


# ---------------------------------------------------------------------------
# 1. Shortlisted candidates list
# ---------------------------------------------------------------------------

@router.get("/tracking/shortlisted", response_model=list[ShortlistRow])
async def list_shortlisted(
    company_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    stage: str | None = None,
    search: str | None = None,
    invoice: str | None = Query(None, pattern="^(yes|no)$"),
    min_ctc: float | None = Query(None, ge=0),
    max_ctc: float | None = Query(None, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every candidate that has been shortlisted for any job (i.e. has a
    pipeline stage), across all companies. Filters:
      - company_id / job_id / stage
      - search: candidate name, email, phone OR role (job title)
      - invoice: "yes" = Joined + invoice raised, "no" = Joined + not raised
      - min_ctc / max_ctc: range on the candidate's Expected CTC (from screening)
    """
    query = (
        select(Assessment)
        .join(Candidate, Candidate.id == Assessment.candidate_id)
        .join(JobPosting, JobPosting.id == Assessment.job_id)
        .where(
            Assessment.deleted_at.is_(None),
            Candidate.deleted_at.is_(None),
            JobPosting.deleted_at.is_(None),
            or_(Assessment.stage != "", Assessment.final_status == "Share to Client"),
        )
        .order_by(Assessment.updated_at.desc())
    )
    if company_id:
        query = query.where(JobPosting.company_id == company_id)
    if job_id:
        query = query.where(Assessment.job_id == job_id)
    if stage:
        query = query.where(Assessment.stage == stage)
    if search:
        like = f"%{search.strip()}%"
        query = query.where(or_(
            Candidate.name.ilike(like),
            Candidate.email.ilike(like),
            Candidate.phone.ilike(like),
            JobPosting.title.ilike(like),
        ))
    if invoice == "yes":
        query = query.where(Assessment.stage == "Joined", Assessment.invoice_raised.is_(True))
    elif invoice == "no":
        query = query.where(Assessment.stage == "Joined", Assessment.invoice_raised.is_(False))
    if min_ctc is not None:
        query = query.where(Assessment.expected_ctc >= min_ctc)
    if max_ctc is not None:
        query = query.where(Assessment.expected_ctc <= max_ctc)

    result = await db.execute(query)
    return await _build_rows(db, list(result.scalars().all()))


@router.get("/tracking/assessments/{assessment_id}", response_model=ShortlistRow)
async def get_tracking_row(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = await _get_assessment(db, assessment_id)
    rows = await _build_rows(db, [assessment])
    if not rows:
        raise HTTPException(404, "Candidate or job no longer exists")
    return rows[0]


# ---------------------------------------------------------------------------
# 3/4/5/6. Stage, submission, selection, invoice
# ---------------------------------------------------------------------------

@router.patch("/assessments/{assessment_id}/tracking", response_model=ShortlistRow)
async def update_tracking(
    assessment_id: uuid.UUID,
    payload: TrackingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = await _get_assessment(db, assessment_id)
    data = payload.model_dump(exclude_unset=True)

    # --- stage ---
    new_stage = assessment.stage or ""
    if data.get("stage"):
        try:
            new_stage = validate_stage(data["stage"])
        except ValueError as e:
            raise HTTPException(400, str(e))

    # --- submission ---
    if "submitted_to" in data and data["submitted_to"] is not None:
        assessment.submitted_to = data["submitted_to"].strip()[:200]
    if "submitted_on" in data:
        assessment.submitted_on = data["submitted_on"]

    # --- selection (CTC / joining date) ---
    if "offered_ctc" in data:
        if data["offered_ctc"] is not None and data["offered_ctc"] < 0:
            raise HTTPException(400, "Offered CTC cannot be negative")
        assessment.offered_ctc = data["offered_ctc"]
    if "joining_date" in data:
        assessment.joining_date = data["joining_date"]

    if new_stage == "Joined" and assessment.joining_date is None:
        raise HTTPException(400, "Enter the joining date before marking the candidate as Joined")

    # --- invoice (only once the candidate has joined) ---
    if "invoice_raised" in data and data["invoice_raised"] is not None:
        if data["invoice_raised"] and new_stage != "Joined":
            raise HTTPException(400, "Invoice can only be raised after the candidate has Joined")
        assessment.invoice_raised = data["invoice_raised"]
        if not data["invoice_raised"]:
            assessment.invoice_date = None
    if assessment.invoice_raised:
        if "invoice_date" in data:
            assessment.invoice_date = data["invoice_date"]
        if assessment.invoice_date is None:
            assessment.invoice_date = date.today()

    if new_stage != (assessment.stage or ""):
        change_stage(db, assessment, new_stage, current_user.id, data.get("stage_note", ""))

    await db.commit()
    await db.refresh(assessment)
    rows = await _build_rows(db, [assessment])
    if not rows:
        raise HTTPException(404, "Candidate or job no longer exists")
    return rows[0]


@router.get("/assessments/{assessment_id}/stage-history", response_model=list[StageHistoryOut])
async def stage_history(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_assessment(db, assessment_id)
    result = await db.execute(
        select(AssessmentStageHistory)
        .where(AssessmentStageHistory.assessment_id == assessment_id)
        .order_by(AssessmentStageHistory.changed_at.desc())
    )
    entries = result.scalars().all()
    users = await _user_names(db, {e.changed_by for e in entries})
    return [
        {
            "id": e.id,
            "assessment_id": e.assessment_id,
            "from_stage": e.from_stage,
            "to_stage": e.to_stage,
            "note": e.note,
            "changed_by_name": users.get(e.changed_by),
            "changed_at": e.changed_at,
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# 2/3. Follow-ups & interviews
# ---------------------------------------------------------------------------

@router.get("/assessments/{assessment_id}/follow-ups", response_model=list[FollowUpOut])
async def list_follow_ups(
    assessment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Follow-ups for one candidate+job, newest first. A rescheduled
    follow-up appears once, with its earlier dates in previous_schedules."""
    await _get_assessment(db, assessment_id)
    result = await db.execute(
        select(FollowUp)
        .where(FollowUp.assessment_id == assessment_id, FollowUp.deleted_at.is_(None))
        .order_by(FollowUp.scheduled_at.desc())
    )
    return await _grouped_follow_ups(db, list(result.scalars().all()))


@router.get("/candidates/{candidate_id}/follow-ups", response_model=list[FollowUpOut])
async def list_candidate_follow_ups(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Candidate-wise follow-ups across every job the candidate is in."""
    result = await db.execute(
        select(FollowUp)
        .where(FollowUp.candidate_id == candidate_id, FollowUp.deleted_at.is_(None))
        .order_by(FollowUp.scheduled_at.desc())
    )
    return await _grouped_follow_ups(db, list(result.scalars().all()))


@router.post("/assessments/{assessment_id}/follow-ups", response_model=FollowUpOut)
async def create_follow_up(
    assessment_id: uuid.UUID,
    payload: FollowUpCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = await _get_assessment(db, assessment_id)
    if payload.follow_up_type not in FOLLOW_UP_TYPES:
        raise HTTPException(400, f"Invalid follow-up type. Allowed: {', '.join(FOLLOW_UP_TYPES)}")

    follow_up = FollowUp(
        assessment_id=assessment.id,
        candidate_id=assessment.candidate_id,
        job_id=assessment.job_id,
        follow_up_type=payload.follow_up_type,
        scheduled_at=payload.scheduled_at,
        status="Scheduled",
        notes=payload.notes.strip(),
        created_by=current_user.id,
    )
    db.add(follow_up)

    # Scheduling an interview moves a Shortlisted/Submitted candidate to the
    # Interview stage automatically (never backwards).
    if "Interview" in payload.follow_up_type and (assessment.stage or "") in ("", "Shortlisted", "Submitted"):
        change_stage(db, assessment, "Interview", current_user.id, f"{payload.follow_up_type} scheduled")

    await db.commit()
    await db.refresh(follow_up)
    candidates, jobs, companies = await _labels_for(db, {follow_up.job_id}, {follow_up.candidate_id})
    return _follow_up_out(follow_up, candidates, jobs, companies, {current_user.id: current_user.name})


@router.patch("/follow-ups/{follow_up_id}", response_model=FollowUpOut)
async def update_follow_up(
    follow_up_id: uuid.UUID,
    payload: FollowUpUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update status/outcome/notes. With `reschedule_to`, the current row is
    closed as "Rescheduled" and the NEW row is returned."""
    follow_up = await db.get(FollowUp, follow_up_id)
    if not follow_up or follow_up.deleted_at is not None:
        raise HTTPException(404, "Follow-up not found")
    data = payload.model_dump(exclude_unset=True)

    if data.get("status") and data["status"] not in FOLLOW_UP_STATUSES:
        raise HTTPException(400, f"Invalid status. Allowed: {', '.join(FOLLOW_UP_STATUSES)}")
    if data.get("follow_up_type") and data["follow_up_type"] not in FOLLOW_UP_TYPES:
        raise HTTPException(400, f"Invalid follow-up type. Allowed: {', '.join(FOLLOW_UP_TYPES)}")

    if data.get("outcome") is not None:
        follow_up.outcome = data["outcome"].strip()
    if data.get("notes") is not None:
        follow_up.notes = data["notes"].strip()
    if data.get("follow_up_type"):
        follow_up.follow_up_type = data["follow_up_type"]

    result_row = follow_up
    if data.get("reschedule_to") and follow_up.status != "Scheduled":
        raise HTTPException(400, "Only a Scheduled follow-up can be rescheduled")
    if data.get("reschedule_to"):
        follow_up.status = "Rescheduled"
        follow_up.completed_at = datetime.now(timezone.utc)
        result_row = FollowUp(
            rescheduled_from_id=follow_up.id,
            assessment_id=follow_up.assessment_id,
            candidate_id=follow_up.candidate_id,
            job_id=follow_up.job_id,
            follow_up_type=follow_up.follow_up_type,
            scheduled_at=data["reschedule_to"],
            status="Scheduled",
            notes=follow_up.notes,
            created_by=current_user.id,
        )
        db.add(result_row)
    elif data.get("status"):
        follow_up.status = data["status"]
        follow_up.completed_at = None if data["status"] == "Scheduled" else datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(result_row)
    chain = await db.execute(
        select(FollowUp).where(FollowUp.assessment_id == result_row.assessment_id, FollowUp.deleted_at.is_(None))
    )
    grouped = await _grouped_follow_ups(db, list(chain.scalars().all()))
    return next((g for g in grouped if g["id"] == result_row.id), grouped[0])


@router.delete("/follow-ups/{follow_up_id}", status_code=204)
async def delete_follow_up(
    follow_up_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete -- for a follow-up entered by mistake. Also removes its
    earlier (rescheduled) dates, since they are shown as part of it."""
    follow_up = await db.get(FollowUp, follow_up_id)
    if not follow_up or follow_up.deleted_at is not None:
        raise HTTPException(404, "Follow-up not found")
    now = datetime.now(timezone.utc)
    current: FollowUp | None = follow_up
    seen: set[uuid.UUID] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        current.deleted_at = now
        current = await db.get(FollowUp, current.rescheduled_from_id) if current.rescheduled_from_id else None
    await db.commit()


# ---------------------------------------------------------------------------
# Dashboard lists
# ---------------------------------------------------------------------------

@router.get("/tracking/follow-ups/due", response_model=list[FollowUpOut])
async def follow_ups_due(
    days: int = Query(7, ge=0, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every still-Scheduled follow-up that is overdue or due within the next
    `days` days, oldest first. The frontend splits it into Overdue / Today /
    Upcoming using the browser's local date."""
    until = datetime.now(timezone.utc) + timedelta(days=days + 1)
    result = await db.execute(
        select(FollowUp)
        .join(Candidate, Candidate.id == FollowUp.candidate_id)
        .where(
            FollowUp.status == "Scheduled",
            FollowUp.deleted_at.is_(None),
            FollowUp.scheduled_at <= until,
            Candidate.deleted_at.is_(None),
        )
        .order_by(FollowUp.scheduled_at.asc())
        .limit(200)
    )
    items = result.scalars().all()
    candidates, jobs, companies = await _labels_for(
        db, {f.job_id for f in items}, {f.candidate_id for f in items}
    )
    users = await _user_names(db, {f.created_by for f in items})
    return [_follow_up_out(f, candidates, jobs, companies, users) for f in items]


@router.get("/tracking/invoice-status", response_model=list[ShortlistRow])
async def invoice_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Selected + Joined candidates with their invoice status -- pending
    invoices (Joined, invoice_raised = NO) first."""
    result = await db.execute(
        select(Assessment)
        .where(Assessment.deleted_at.is_(None), Assessment.stage.in_(["Selected", "Joined"]))
        .order_by(Assessment.joining_date.asc().nulls_last())
    )
    rows = await _build_rows(db, list(result.scalars().all()))
    rows.sort(key=lambda r: (
        0 if (r["stage"] == "Joined" and not r["invoice_raised"]) else 1 if r["stage"] == "Selected" else 2,
    ))
    return rows