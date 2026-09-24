import uuid
from datetime import datetime
from pydantic import BaseModel


class AssessmentCreate(BaseModel):
    """Fields a recruiter fills in during/after a screening call. All optional
    at the Pydantic layer so a partial PATCH-style update also validates —
    completeness is enforced at the "mark screened" transition, not here."""
    current_ctc: float | None = None
    expected_ctc: float | None = None
    notice_period_days: int | None = None
    current_location: str = ""
    preferred_location: str = ""
    cv_relevance: str = ""
    experience_match: str = ""
    skills_match: str = ""
    industry_alignment: str = ""
    job_stability: str = ""
    communication: str = ""
    interest_level: str = ""
    notice_fit: str = ""
    salary_alignment: str = ""
    role_notes: str = ""
    skills_notes: str = ""
    achievements: str = ""
    reason_for_change: str = ""
    red_flags: str = ""
    final_status: str = "Share to Client"
    recruiter_remarks: str = ""


class AssessmentOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    current_ctc: float | None
    expected_ctc: float | None
    notice_period_days: int | None
    current_location: str
    preferred_location: str
    cv_relevance: str
    experience_match: str
    skills_match: str
    industry_alignment: str
    job_stability: str
    communication: str
    interest_level: str
    notice_fit: str
    salary_alignment: str
    role_notes: str
    skills_notes: str
    achievements: str
    reason_for_change: str
    red_flags: str
    final_status: str
    recruiter_remarks: str
    screened: bool
    sent_to_client: bool
    client_feedback: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class AssessmentScored(AssessmentOut):
    """AssessmentOut plus the computed score breakdown, for pipeline/detail views."""
    # Joined in from the related Candidate row so the frontend never has to
    # make a second /candidates call just to label a pipeline/assessment row.
    candidate_name: str
    candidate_email: str
    candidate_experience_years: float
    candidate_current_company: str
    candidate_status: str | None = None  # queued | extracting | embedding | ready | failed | needs_review
    ai_score: int | None = None
    # "ai_pipeline" = a real GPT-5 MatchResult was found for this pair;
    # "estimate" = matching hasn't run yet and this is the cheap keyword-
    # overlap fallback. Lets the frontend label the score honestly instead
    # of parsing the "rough estimate" text out of `flags`.
    ai_source: str | None = None
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    assessment_score: int | None = None
    final_score: int | None = None
    bucket: str
    flags: list[dict] = []
    adjustments: list[dict] = []


class ClientFeedbackUpdate(BaseModel):
    feedback: str  # "Interested" | "Not Interested"