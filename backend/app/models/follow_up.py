import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


FOLLOW_UP_TYPES = [
    "Screening Call", "Interview - Round 1", "Interview - Round 2",
    "Interview - HR", "Client Interview", "Offer Discussion",
    "Joining Confirmation", "General Follow-up",
]
FOLLOW_UP_STATUSES = ["Scheduled", "Completed", "Rescheduled", "Cancelled", "No Show"]


class FollowUp(Base):
    """One scheduled follow-up or interview for a (candidate, job) pair.

    Rows are never overwritten to change the date: rescheduling marks the
    old row "Rescheduled" and creates a new "Scheduled" row that points back
    at it via `rescheduled_from_id`. The API shows each chain as ONE
    follow-up (the latest row) with the earlier dates listed inside it.
    """
    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assessments.id"), index=True)
    # Denormalised from the assessment so the dashboard's due/overdue list
    # can filter and label rows without an extra join per row.
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_postings.id"), index=True)

    # Set on a row created by rescheduling -> the row it replaced.
    rescheduled_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("follow_ups.id"), nullable=True, index=True
    )

    follow_up_type: Mapped[str] = mapped_column(String(40), default="General Follow-up")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="Scheduled", index=True)
    notes: Mapped[str] = mapped_column(String, default="")
    outcome: Mapped[str] = mapped_column(String, default="")

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)