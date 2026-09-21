import uuid
from datetime import datetime
from pydantic import BaseModel


class JobPostingCreate(BaseModel):
    company_id: uuid.UUID
    title: str
    locations: list[str] = []
    budget_min: float = 0
    budget_max: float = 0
    experience_min: float = 0
    experience_max: float = 0
    max_notice_days: int = 45
    required_skills: list[str] = []
    raw_text: str = ""  # optional pasted JD text, for the AI extraction pipeline later


class JobPostingOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    title: str
    locations: list[str]
    budget_min: float
    budget_max: float
    experience_min: float
    experience_max: float
    max_notice_days: int
    required_skills: list[str]
    status: str
    opened_on: datetime

    class Config:
        from_attributes = True


# --- Structured LLM extraction output shape for a JD (used later, once wired in) ---
class JDExtractionResult(BaseModel):
    required_skills: list[str]
    nice_to_have_skills: list[str]
    min_experience_years: float
    responsibilities: list[str]
    qualifications: list[str]
    hard_requirements: list[str]
