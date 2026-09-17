import uuid
from pydantic import BaseModel


class MatchResultOut(BaseModel):
    candidate_id: uuid.UUID
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    strengths: list[str]
    gaps: list[str]
    recommendation: str  # Shortlist | Review | Pass

    class Config:
        from_attributes = True


class MatchRunRequest(BaseModel):
    top_k: int | None = None  # falls back to settings.default_top_k if omitted
