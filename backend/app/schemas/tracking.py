import uuid
from datetime import datetime, date
from pydantic import BaseModel


class TrackingUpdate(BaseModel):
    """PATCH /assessments/{id}/tracking -- every field optional; only the
    fields actually sent are applied (model_dump(exclude_unset=True))."""
    stage: str | None = None
    stage_note: str = ""
    submitted_to: str | None = None
    submitted_on: datetime | None = None
    offered_ctc: float | None = None
    joining_date: date | None = None
    invoice_raised: bool | None = None
    invoice_date: date | None = None


class StageHistoryOut(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    from_stage: str
    to_stage: str
    note: str
    changed_by_name: str | None = None
    changed_at: datetime


class FollowUpCreate(BaseModel):
    follow_up_type: str = "General Follow-up"
    scheduled_at: datetime
    notes: str = ""


class FollowUpUpdate(BaseModel):
    status: str | None = None
    outcome: str | None = None
    notes: str | None = None
    follow_up_type: str | None = None
    # When set, the current row is marked "Rescheduled" and a NEW
    # "Scheduled" row is created at this time -- keeps the history intact.
    reschedule_to: datetime | None = None


class PreviousSchedule(BaseModel):
    """One earlier date of a follow-up that was later rescheduled."""
    scheduled_at: datetime
    rescheduled_on: datetime | None = None
    reason: str = ""
    by_name: str | None = None


class FollowUpOut(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    follow_up_type: str
    scheduled_at: datetime
    status: str
    notes: str
    outcome: str
    created_by_name: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    # Earlier dates of this follow-up, newest first (empty if never rescheduled)
    previous_schedules: list[PreviousSchedule] = []
    # Display labels (joined in)
    candidate_name: str = ""
    job_title: str = ""
    company_name: str = ""


class ShortlistRow(BaseModel):
    """One row of the Shortlisted candidates page / dashboard lists."""
    assessment_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_name: str
    candidate_email: str
    candidate_phone: str
    job_id: uuid.UUID
    job_title: str
    job_status: str
    company_id: uuid.UUID | None
    company_name: str
    company_active: bool
    final_status: str
    stage: str
    submitted_to: str
    submitted_on: datetime | None
    current_ctc: float | None
    expected_ctc: float | None
    offered_ctc: float | None
    joining_date: date | None
    invoice_raised: bool
    invoice_date: date | None
    next_follow_up_at: datetime | None = None
    next_follow_up_type: str | None = None
    overdue_follow_ups: int = 0
    updated_at: datetime | None
