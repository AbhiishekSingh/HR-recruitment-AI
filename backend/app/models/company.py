import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Company(Base):
    """A client company the agency recruits for. Distinct from `users` (agency staff)."""
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(300))
    industry: Mapped[str] = mapped_column(String(200), default="")
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    gst_number: Mapped[str] = mapped_column(String(15), default="")
    tier: Mapped[str] = mapped_column(String(50), default="Standard")  # Standard | Premium
    onboarded_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Path to the uploaded company details document (PDF/Word) on disk --
    # same storage pattern as Candidate.file_path. Null until one is
    # attached; a company can be onboarded without a document.
    document_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Soft delete: null = active. Set instead of a hard DELETE so historical
    # jobs/assessments tied to this company stay intact and auditable.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
