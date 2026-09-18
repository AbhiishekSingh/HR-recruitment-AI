import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, Index, func, desc
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchResult(Base):
    """One row per (job, candidate) — the CURRENT AI score for that pair, not a
    log of every scoring run. Unique on (job_id, candidate_id): re-matching a
    job upserts this row (via requirements_hash below) instead of piling up
    stale duplicates. See services/search + workers/tasks_matching for the
    upsert logic that relies on this constraint."""
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_id", name="uq_match_results_job_candidate"),
        # Composite index backing the pipeline's sorted-shortlist query
        # (WHERE job_id = ... ORDER BY score DESC). Matches the migration's
        # explicit DESC index exactly.
        Index("ix_match_results_job_score", "job_id", desc("score")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_postings.id"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)  # 0-100
    matched_skills: Mapped[dict] = mapped_column(JSONB, default=dict)
    missing_skills: Mapped[dict] = mapped_column(JSONB, default=dict)
    strengths: Mapped[dict] = mapped_column(JSONB, default=dict)
    gaps: Mapped[dict] = mapped_column(JSONB, default=dict)
    recommendation: Mapped[str] = mapped_column(String(20))  # Shortlist | Review | Pass
    # Hash of (job.requirements, candidate profile's extraction_model_version) at
    # scoring time. Unchanged hash on a re-match = skip, no new LLM call (see
    # project doc, Stage 2). Nullable: rows from before this column existed have
    # no hash yet and get one the next time that pair is scored.
    requirements_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    model_version: Mapped[str] = mapped_column(String(100))
