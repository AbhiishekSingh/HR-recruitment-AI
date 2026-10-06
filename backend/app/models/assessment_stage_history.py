import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssessmentStageHistory(Base):
    """Append-only log of every stage change on an assessment
    (Shortlisted -> Submitted -> Interview -> Selected -> Joined, or an
    outcome such as Rejected / On Hold / Offer Declined)."""
    __tablename__ = "assessment_stage_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assessments.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(30), default="")
    to_stage: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String, default="")
    changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
