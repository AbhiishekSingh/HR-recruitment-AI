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
    # Optional manual entry at creation time -- most candidates get these
    # auto-classified from their resume during ingestion instead (see
    # tasks_ingestion.py), but the manual "Add Candidate" form allows
    # setting them directly for a candidate with no resume file yet.
    sector: str | None = None
    position_role: str | None = None


class CandidateUpdate(BaseModel):
    """Partial update -- used by PATCH /candidates/{id}, currently just for
    manually overriding/correcting the AI-classified sector/position_role.
    All fields optional; only provided ones are applied."""
    sector: str | None = None
    position_role: str | None = None
    # true = recruiter confirmed this is NOT a duplicate; clears the flag
    clear_duplicate: bool | None = None


class CandidateOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: str
    current_company: str
    experience_years: float
    resume_skills: list[str]
    resume_summary: str
    file_path: str | None
    status: str
    status_detail: str = ""
    added_on: datetime
    sector: str | None = None
    position_role: str | None = None
    possible_duplicate_of: uuid.UUID | None = None
    possible_duplicate_of_name: str | None = None
    # true when queued/extracting/embedding for longer than 15 minutes
    stuck: bool = False

    class Config:
        from_attributes = True


# --- Bulk upload (batched, skip-don't-crash) ---

class UploadFailure(BaseModel):
    filename: str
    reason: str


class UploadBatchResult(BaseModel):
    """POST /candidates/upload-batch -- one bad file never fails the
    whole batch; it is reported in `failed` and the rest carry on."""
    created: list[CandidateOut]
    failed: list[UploadFailure]


class CandidateIdsRequest(BaseModel):
    ids: list[uuid.UUID]


class CandidateOverview(BaseModel):
    """Totals for the Candidates landing page, so the sector cards plus
    the status cards always add up to the real number of resumes."""
    total: int
    classified: int        # has a sector -> appears on a sector card
    needs_attention: int   # failed / needs_review / stuck
    processing: int        # still queued / extracting / embedding (not stuck)
    unclassified: int      # processed fine but no sector yet
    duplicates: int        # flagged as a possible duplicate


class FingerprintRequest(BaseModel):
    hashes: list[str]


class FingerprintMatch(BaseModel):
    hash: str
    candidate_id: uuid.UUID
    name: str


class IngestionStatusRow(BaseModel):
    id: uuid.UUID
    name: str
    status: str            # queued | extracting | embedding | ready | needs_review | failed
    status_detail: str
    stuck: bool            # in progress for longer than STUCK_AFTER_MINUTES
    has_resume_file: bool


class SectorCount(BaseModel):
    sector: str
    count: int


class DuplicateMatch(BaseModel):
    """One existing candidate whose email or phone matches the resume just
    picked for upload, for POST /candidates/check-duplicate. `matched_on`
    tells the frontend which field(s) matched, so the confirmation prompt
    can say something more specific than just "a candidate matched"."""
    candidate_id: uuid.UUID
    name: str
    email: str
    phone: str
    status: str
    added_on: datetime
    matched_on: list[str]  # "email" and/or "phone"


class DuplicateCheckResult(BaseModel):
    """Response for POST /candidates/check-duplicate. `checked` is False
    when no pre-check was possible at all (e.g. a scanned PDF with no text
    layer -- see contact_hint.py's docstring for why this endpoint doesn't
    fall back to a real LLM extraction just to make that case work) --
    distinguished from `checked=True, matches=[]`, which means the check DID
    run and genuinely found nothing."""
    checked: bool
    matches: list[DuplicateMatch] = []


class ResumeSearchMatch(BaseModel):
    """One matching line from a candidate's resume raw_text, for
    GET /candidates/search-resumes. `highlights` gives the [start, end)
    character offsets of every occurrence of the search term within `text`
    (there can be more than one per line) so the frontend can wrap exactly
    those spans in a <mark> without re-doing the matching client-side --
    important since the highlight has to follow the same
    normalized/case-insensitive matching the backend used to find the line
    in the first place, not a naive client-side re-search."""
    line_number: int
    text: str
    highlights: list[list[int]]


class ResumeSearchResult(BaseModel):
    """One candidate's worth of matches for a full-text resume search.
    `has_more_matches` is set when this candidate's matches were truncated
    at the per-candidate cap (see candidates.py's search-resumes endpoint)
    -- the frontend can use it to say "+N more matches, open resume to see
    all" rather than silently dropping them."""
    candidate_id: uuid.UUID
    candidate_name: str
    sector: str | None = None
    position_role: str | None = None
    status: str
    has_resume_file: bool
    matches: list[ResumeSearchMatch]
    has_more_matches: bool = False


# --- Structured LLM extraction output shape (used later, once wired in) ---
class ResumeExtractionResult(BaseModel):
    skills: list[str]
    work_history: list[dict]
    education: list[dict]
    certifications: list[str]
    total_experience_years: float