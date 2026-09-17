import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchResult(Base):
    """One row per (job, candidate) scoring — the audit trail."""
    __tablename__ = "match_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_postings.id"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)  # 0-100
    matched_skills: Mapped[dict] = mapped_column(JSONB, default=dict)
    missing_skills: Mapped[dict] = mapped_column(JSONB, default=dict)
    strengths: Mapped[dict] = mapped_column(JSONB, default=dict)
    gaps: Mapped[dict] = mapped_column(JSONB, default=dict)
    recommendation: Mapped[str] = mapped_column(String(20))  # Shortlist | Review | Pass
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    model_version: Mapped[str] = mapped_column(String(100))
