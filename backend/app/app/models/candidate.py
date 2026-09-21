import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Float, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Candidate(Base):
    """One record per real person. Independent of any job — a person can be
    considered for multiple requisitions without duplicate records. PII lives
    here, isolated from scoring/matching tables.

    resume_skills / experience_years / etc. are manually entered or bulk-upload
    entered for now (matching the ATS's actual staffing workflow, where a
    resume needs to be usable immediately, before any AI processing runs).
    These get superseded/enriched by candidate_profiles once the real
    extraction pipeline (GPT-5) is wired in for this record.
    """
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(50), default="")
    current_company: Mapped[str] = mapped_column(String(300), default="")
    experience_years: Mapped[float] = mapped_column(Float, default=0)
    resume_skills: Mapped[list] = mapped_column(JSONB, default=list)
    resume_summary: Mapped[str] = mapped_column(String, default="")

    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="queued")
    # queued | extracting | embedding | ready | failed | needs_review
    # ("ready" for now just means "usable in the pipeline" — real AI status
    # transitions get wired in when extraction/embedding work happens)

    added_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Soft delete: null = active. candidate_profiles/embeddings/match_results
    # keep pointing at this row's id even after a soft delete, so AI history
    # for the person isn't orphaned by a hard DELETE.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
