import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIUsageLog(Base):
    """One row per AI API call (including retries -- each attempt is billed),
    with the exact token counts OpenAI reported and the cost worked out from
    services/ai_usage.py's price table. Powers the Analytics "AI usage" card."""
    __tablename__ = "ai_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    # resume_extraction | resume_vision | resume_transcription | jd_reading |
    # jd_requirements | candidate_scoring | embedding
    task: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    priced: Mapped[bool] = mapped_column(Boolean, default=True)  # False = model not in the price table
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job_postings.id"), nullable=True, index=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("candidates.id"), nullable=True, index=True)
