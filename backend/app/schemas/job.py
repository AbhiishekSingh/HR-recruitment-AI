import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SkillGroup(BaseModel):
    """One scoring group: any one of `skills` (or their synonyms) found in a
    resume counts as the whole group matched."""
    name: str = ""
    type: Literal["must", "nice", "soft"] = "must"
    skills: list[str] = []
    synonyms: list[str] = []


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
    # From POST /jobs/parse-jd: links the uploaded JD file to this new job.
    jd_upload_token: str | None = None
    # From POST /jobs/parse-jd: structured requirements (incl. nice-to-have
    # skills) so AI matching doesn't extract the same JD again.
    requirements: dict | None = None
    # Scoring settings (AI-suggested from the JD, edited by HR). Omitted =
    # automatic groups from required_skills.
    skill_groups: list[SkillGroup] | None = None
    related_titles: list[str] | None = None


class JobPostingUpdate(BaseModel):
    """PATCH /jobs/{id} -- only the fields sent are changed."""
    title: str | None = None
    locations: list[str] | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    max_notice_days: int | None = None
    required_skills: list[str] | None = None
    raw_text: str | None = None
    requirements: dict | None = None
    skill_groups: list[SkillGroup] | None = None
    related_titles: list[str] | None = None


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
    raw_text: str = ""
    has_jd_file: bool = False
    jd_file_name: str | None = None
    # Scoring settings in use -- saved ones, or the automatic default.
    skill_groups: list[SkillGroup] = []
    related_titles: list[str] = []
    has_custom_groups: bool = False

    class Config:
        from_attributes = True


class JobStatusUpdate(BaseModel):
    status: str  # "Open" (shown as Active) | "Closed" (shown as Inactive)


# --- Structured LLM extraction output shape for a JD (used later, once wired in) ---
class JDExtractionResult(BaseModel):
    required_skills: list[str]
    nice_to_have_skills: list[str]
    min_experience_years: float
    responsibilities: list[str]
    qualifications: list[str]
    hard_requirements: list[str]



class JDFormFields(BaseModel):
    """Pre-fill values read from an uploaded JD. None/[] = not in the JD."""
    title: str | None = None
    locations: list[str] = []
    budget_min: float | None = None
    budget_max: float | None = None
    experience_min: float | None = None
    experience_max: float | None = None
    max_notice_days: int | None = None
    required_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    skill_groups: list[SkillGroup] = []
    related_titles: list[str] = []


class JDParseResult(BaseModel):
    upload_token: str | None = None   # pass back on POST /jobs to attach the file
    file_name: str
    fields: JDFormFields
    missing: list[str]                # form fields the JD didn't provide
    requirements: dict = {}
    raw_text: str = ""
    error: str | None = None          # AI couldn't read it -> fill manually


class JDAttachResult(BaseModel):
    """PUT /jobs/{id}/jd -- the file is attached; `parse` holds values read
    from it so HR can choose to update the job's fields."""
    job: JobPostingOut
    parse: JDParseResult
