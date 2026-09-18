import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, Float, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Assessment(Base):
    """One screening record for a (candidate, job) pair. A candidate can have
    many assessments (one per role applied to) — this is the join entity, and
    it holds everything a recruiter fills in during/after a screening call.

    `screened=False` is a "Pending Screening" stub: created the moment a
    resume is added to a job's pipeline, before any screening-call data
    exists. All the enum/rating/note fields stay blank until a recruiter
    actually screens the candidate and fills the form in.

    AI_score is a placeholder column for now — real GPT-5 scoring will
    populate this later (see match_results/candidate_profiles for where that
    pipeline already lives); it is NOT computed here yet.
    """
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_postings.id"), index=True)

    # --- Compensation / logistics ---
    current_ctc: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_ctc: Mapped[float | None] = mapped_column(Float, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_location: Mapped[str] = mapped_column(String(200), default="")
    preferred_location: Mapped[str] = mapped_column(String(200), default="")

    # --- Screening-call ratings (enums as free strings for now, matching the
    # prototype's option sets: Strong/Partial/Low, Good/Average/Poor, etc.) ---
    cv_relevance: Mapped[str] = mapped_column(String(20), default="")       # Yes | No
    experience_match: Mapped[str] = mapped_column(String(20), default="")  # Strong | Partial | Low
    skills_match: Mapped[str] = mapped_column(String(20), default="")      # Strong | Partial | Low
    industry_alignment: Mapped[str] = mapped_column(String(20), default="")  # Yes | No
    job_stability: Mapped[str] = mapped_column(String(30), default="")     # Stable | Moderate | Frequent Changes
    communication: Mapped[str] = mapped_column(String(20), default="")     # Good | Average | Poor
    interest_level: Mapped[str] = mapped_column(String(20), default="")    # High | Moderate | Low
    notice_fit: Mapped[str] = mapped_column(String(20), default="")        # Yes | No
    salary_alignment: Mapped[str] = mapped_column(String(20), default="")  # Yes | No

    # --- Free-text screening notes ---
    role_notes: Mapped[str] = mapped_column(String, default="")
    skills_notes: Mapped[str] = mapped_column(String, default="")
    achievements: Mapped[str] = mapped_column(String, default="")
    reason_for_change: Mapped[str] = mapped_column(String, default="")
    red_flags: Mapped[str] = mapped_column(String, default="")

    # --- Status / outcome ---
    final_status: Mapped[str] = mapped_column(String(30), default="Pending Screening")
    # Pending Screening | Share to Client | Hold | Reject
    recruiter_remarks: Mapped[str] = mapped_column(String, default="")
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    screened: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_to_client: Mapped[bool] = mapped_column(Boolean, default=False)
    client_feedback: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Interested | Not Interested

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft delete: null = active. A screening record is part of the decision
    # audit trail (who screened whom, when, and why) — never hard-deleted.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
