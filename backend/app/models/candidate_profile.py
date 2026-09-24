import uuid

from sqlalchemy import ForeignKey, Float, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CandidateProfile(Base):
    """Structured GPT-5 extraction output for a resume."""
    __tablename__ = "candidate_profiles"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidates.id"), primary_key=True
    )
    raw_text: Mapped[str] = mapped_column(String)
    skills: Mapped[dict] = mapped_column(JSONB, default=dict)
    work_history: Mapped[dict] = mapped_column(JSONB, default=dict)
    education: Mapped[dict] = mapped_column(JSONB, default=dict)
    certifications: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Was mapped_column(Integer, ...) despite the Python-side float type hint
    # -- asyncpg is strict about parameter types and raises a DataError the
    # first time GPT-5 extracts a non-whole-number value (e.g. 4.5 years).
    # See migration f1a2b3c4d5e6.
    total_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_model_version: Mapped[str] = mapped_column(String(100))
