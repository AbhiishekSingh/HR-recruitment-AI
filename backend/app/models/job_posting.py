import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, Float, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.models.candidate_embedding import EMBEDDING_DIM


class JobPosting(Base):
    """A job requisition, belonging to a client Company (not a user)."""
    __tablename__ = "job_postings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    title: Mapped[str] = mapped_column(String(300))
    locations: Mapped[list] = mapped_column(JSONB, default=list)
    budget_min: Mapped[float] = mapped_column(Float, default=0)
    budget_max: Mapped[float] = mapped_column(Float, default=0)
    experience_min: Mapped[float] = mapped_column(Float, default=0)
    experience_max: Mapped[float] = mapped_column(Float, default=0)
    max_notice_days: Mapped[int] = mapped_column(Integer, default=45)
    required_skills: Mapped[list] = mapped_column(JSONB, default=list)  # manually entered for now
    status: Mapped[str] = mapped_column(String(50), default="Open")  # Open | Closed

    # AI extraction fields — populated later once the real GPT-5 pipeline is wired in.
    # raw_text is the pasted JD; requirements/embedding stay null until that work happens.
    raw_text: Mapped[str] = mapped_column(String, default="")
    requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    opened_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    target_close: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Soft delete: null = active. Closing a requisition uses `status`;
    # deleted_at is only for "this job shouldn't have existed" cases, so
    # assessments/match_results tied to it stay intact for audit purposes.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
