import uuid
from datetime import datetime
from pydantic import BaseModel


class CandidateCreate(BaseModel):
    name: str
    email: str
    phone: str = ""
    current_company: str = ""
    experience_years: float = 0
    resume_skills: list[str] = []
    resume_summary: str = ""


class CandidateOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: str
    current_company: str
    experience_years: float
    resume_skills: list[str]
    resume_summary: str
    status: str
    added_on: datetime

    class Config:
        from_attributes = True


# --- Structured LLM extraction output shape (used later, once wired in) ---
class ResumeExtractionResult(BaseModel):
    skills: list[str]
    work_history: list[dict]
    education: list[dict]
    certifications: list[str]
    total_experience_years: float
