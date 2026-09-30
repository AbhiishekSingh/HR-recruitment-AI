import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, String, cast

from app.api.deps import get_db, get_current_user
from app.config import settings
from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.assessment import Assessment
from app.models.job_posting import JobPosting
from app.models.user import User
from app.schemas.candidate import (
    CandidateCreate, CandidateOut, CandidateUpdate, SectorCount,
    ResumeSearchMatch, ResumeSearchResult,
    DuplicateMatch, DuplicateCheckResult,
)
from app.services.extraction.text_router import extract_text
from app.services.extraction.contact_hint import extract_email_hint, extract_phone_hint, normalize_phone
from app.services.search.term_normalization import expand_qualification, expand_skill, normalize_for_sql
from app.workers.tasks_ingestion import ingest_resume_task

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5MB, enforced server-side (never trust the browser alone)


def _save_resume_file(candidate_id: uuid.UUID, filename: str, contents: bytes) -> str:
    """Validates and writes one resume file to disk, returning the stored
    path. Shared by bulk-upload and the single-candidate (re)upload endpoint
    so there is exactly one place that decides how/where resumes are stored."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {filename}")
    if len(contents) > MAX_RESUME_BYTES:
        raise HTTPException(400, f"{filename} exceeds the 5MB resume size limit")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / f"{candidate_id}{ext}"
    dest_path.write_bytes(contents)
    return str(dest_path)


def _delete_resume_file(file_path: str | None) -> None:
    """Removes a resume file from disk if it exists. Never raises — a
    missing file on disk (already deleted, moved, etc.) shouldn't block the
    database update that's about to happen."""
    if not file_path:
        return
    path = Path(file_path)
    if path.exists():
        path.unlink()


@router.post("", response_model=CandidateOut)
async def create_candidate(
    payload: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Directory 'Add one candidate' flow — a person + their resume details,
    independent of any job. Real file/AI extraction is attached separately
    via /candidates/upload if a file is provided at bulk-upload time; this
    endpoint is for the manual-entry path the ATS pipeline actually needs
    today (matching the prototype's Step A)."""
    existing = await db.execute(
        select(Candidate).where(Candidate.email == payload.email.lower(), Candidate.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "A candidate with this email already exists")

    candidate = Candidate(
        **payload.model_dump(exclude={"email"}), email=payload.email.lower(), status="ready"
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.post("/upload", response_model=list[CandidateOut])
async def bulk_upload_resumes(
    files: list[UploadFile] = File(...),
    job_id: uuid.UUID | None = Form(None),
    # Pins every candidate created by this call to a specific sector,
    # bypassing GPT-5's auto-classification for it entirely -- set by
    # SectorPicker on the frontend, either from its built-in suggested list
    # or a brand-new name the recruiter typed. Free text, not validated
    # against VALID_SECTORS: a manually-chosen sector is explicitly allowed
    # to be one GPT-5 itself could never pick (see update_candidate's
    # matching comment) -- only trimmed and length-capped as a sanity check.
    sector: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk resume upload for a specific job's pipeline. Each file becomes a
    Candidate record (or matches an existing one by filename-derived name —
    real de-dup by email happens once the recruiter fills in the candidate's
    email during screening) plus a 'Pending Screening' Assessment stub for
    that job, exactly matching the prototype's bulk-upload flow.

    File text extraction + GPT-5 structuring still runs via the existing
    ingestion pipeline (Celery) so the AI foundation stays wired in, even
    though the ATS pipeline doesn't depend on its output yet. When `sector`
    is given, it's set directly on each created Candidate row -- since
    tasks_ingestion.py's guarded-sync only fills sector/position_role when
    currently blank (never overwrites an already-set value), a pinned
    sector here is never later clobbered by the AI classification the
    ingestion pipeline still runs on the resume's actual content."""
    if job_id:
        job = await db.get(JobPosting, job_id)
        if not job:
            raise HTTPException(404, "Job posting not found")

    pinned_sector = sector.strip() if sector and sector.strip() else None
    if pinned_sector and len(pinned_sector) > 50:
        raise HTTPException(400, "sector must be 50 characters or fewer")

    created = []

    for file in files:
        candidate_id = uuid.uuid4()
        contents = await file.read()
        dest_path = _save_resume_file(candidate_id, file.filename, contents)

        guessed_name = Path(file.filename).stem.replace("_", " ").replace("-", " ").title()
        candidate = Candidate(
            id=candidate_id, name=guessed_name, email=f"{candidate_id}@pending.local",
            file_path=dest_path, status="queued", sector=pinned_sector,
        )
        db.add(candidate)
        await db.flush()

        if job_id:
            db.add(Assessment(candidate_id=candidate.id, job_id=job_id, final_status="Pending Screening", screened=False))

        await db.commit()
        await db.refresh(candidate)

        ingest_resume_task.delay(str(candidate.id), dest_path)
        created.append(candidate)

    return created


@router.post("/check-duplicate", response_model=DuplicateCheckResult)
async def check_duplicate_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called by the frontend BEFORE actually uploading a resume, so a
    recruiter can be warned "this candidate might already be on file --
    replace / keep both / cancel?" and choose, instead of silently ending up
    with a duplicate candidate row every time the same person's resume gets
    uploaded twice (e.g. from two different job postings, or a recruiter not
    realizing someone was already added).

    Matches on email and/or phone number pulled from the resume via a cheap
    regex pass (see contact_hint.py for why this isn't a real LLM
    extraction), against every active (non-deleted) candidate's stored
    email/phone. Does not create, modify, or queue anything -- purely a
    read-only check; the actual create/replace happens via the existing
    POST /candidates/upload or PUT /candidates/{id}/resume once the
    recruiter has decided what to do with the answer."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    contents = await file.read()
    # extract_text() (and the pdfplumber/docx libraries under it) needs a
    # real file path, not raw bytes -- written to a throwaway temp file
    # rather than duplicating the extraction logic to accept bytes, and
    # cleaned up in `finally` regardless of how extraction goes.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        try:
            text = extract_text(tmp_path)
        except Exception:
            # Scanned PDF (no text layer) or a genuinely unreadable file --
            # no cheap way to get contact info without a real LLM
            # extraction, which this endpoint deliberately avoids (see
            # contact_hint.py). The pre-check is simply skipped for this
            # file; it still goes through the normal ingestion pipeline
            # (and gets a real duplicate opportunity via manual review)
            # once uploaded.
            return DuplicateCheckResult(checked=False, matches=[])
    finally:
        os.unlink(tmp_path)

    email_hint = extract_email_hint(text)
    phone_hint = extract_phone_hint(text)
    if not email_hint and not phone_hint:
        return DuplicateCheckResult(checked=True, matches=[])

    # Compared in Python, not SQL: Candidate.phone was itself extracted by
    # GPT-5 from a different resume at a different time and can be in any of
    # several formats ("+91 98765 43210", "9876543210", "098-765-43210"), so
    # there's no single SQL pattern that normalizes it consistently the way
    # normalize_phone() does. Fine at the current candidate-base scale (see
    # search-resumes' similar full-scan note); revisit if this gets slow.
    result = await db.execute(select(Candidate).where(Candidate.deleted_at.is_(None)))
    matches: list[DuplicateMatch] = []
    for candidate in result.scalars().all():
        matched_on = []
        # The "@pending.local" placeholder (bulk-upload identity before
        # ingestion fills in a real email -- see tasks_ingestion.py) must
        # never count as an email match; every unprocessed candidate would
        # otherwise "match" every other one.
        if email_hint and candidate.email.lower() == email_hint and not candidate.email.endswith("@pending.local"):
            matched_on.append("email")
        if phone_hint and candidate.phone and normalize_phone(candidate.phone) == phone_hint:
            matched_on.append("phone")
        if matched_on:
            matches.append(DuplicateMatch(
                candidate_id=candidate.id,
                name=candidate.name,
                email=candidate.email,
                phone=candidate.phone,
                status=candidate.status,
                added_on=candidate.added_on,
                matched_on=matched_on,
            ))

    return DuplicateCheckResult(checked=True, matches=matches)


@router.get("", response_model=list[CandidateOut])
async def list_candidates(
    search: str | None = None,
    sector: str | None = None,
    skills: str | None = None,  # comma-separated; matches a candidate with ANY of these skills
    min_experience: float | None = None,
    max_experience: float | None = None,
    qualification: str | None = None,  # free-text match against education (degree/institution)
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    def _normalized_contains(column, term: str):
        """Matches `term` against `column` (cast to text if it's JSONB)
        after stripping punctuation/casing from BOTH sides, so "B.Sc",
        "b sc" and "BSc" all match each other -- see
        term_normalization.py's module docstring for the full reasoning.
        Postgres's regexp_replace(..., 'g') mirrors this module's
        _normalize() exactly (strip everything but a-z0-9, lowercase)."""
        column_text = cast(column, String) if not isinstance(column, str) else column
        normalized_column = func.regexp_replace(func.lower(column_text), "[^a-z0-9]", "", "g")
        return normalized_column.contains(normalize_for_sql(term))

    def _matches_any_alias(column, term: str, expand) -> list:
        """Expands `term` to its full synonym group (e.g. "bsc" ->
        ["bachelor of science", "bsc", "b.sc", ...]) via `expand`
        (expand_qualification or expand_skill), and returns one
        _normalized_contains condition per alias to OR together -- this is
        what makes "BSc" also match a resume that says "Bachelor of
        Science", not just punctuation/casing variants of "BSc" itself."""
        return [_normalized_contains(column, alias) for alias in expand(term)]

    def _qualification_condition(term: str):
        """education lives on candidate_profiles, not candidates, so
        matching it here (from the plain search box, without an explicit
        `qualification` filter/join active) uses a correlated EXISTS
        subquery rather than a join -- a join would risk duplicating a
        candidate's row if they ever had more than one profile match, and
        would need extra care to combine correctly with the OR'd conditions
        already checking columns on Candidate itself."""
        alias_conditions = _matches_any_alias(CandidateProfile.education, term, expand_qualification)
        return Candidate.id.in_(
            select(CandidateProfile.candidate_id).where(or_(*alias_conditions))
        )

    query = select(Candidate).where(Candidate.deleted_at.is_(None)).order_by(Candidate.added_on.desc())
    if search:
        # The plain search box matches broadly -- not just identity fields,
        # but also skills, position_role and qualification -- so typing
        # "React" or "BSc" here finds candidates without needing the
        # separate Filters panel. All of this queries already-extracted
        # columns (see the `skills` filter's comment for why re-scanning
        # the resume itself is never on this path), through the same
        # normalized + alias-aware matching as the dedicated filters below.
        search = search.strip()
        q = f"%{search.lower()}%"
        conditions = [
            Candidate.name.ilike(q),
            Candidate.email.ilike(q),
            Candidate.phone.ilike(q),
            Candidate.current_company.ilike(q),
            *_matches_any_alias(Candidate.position_role, search, expand_skill),
            *_matches_any_alias(Candidate.resume_skills, search, expand_skill),
            _qualification_condition(search),
        ]
        query = query.where(or_(*conditions))
    if sector:
        query = query.where(Candidate.sector == sector)
    if min_experience is not None:
        query = query.where(Candidate.experience_years >= min_experience)
    if max_experience is not None:
        query = query.where(Candidate.experience_years <= max_experience)
    if skills:
        # resume_skills is a JSONB list (e.g. ["React", "TypeScript"]). Each
        # requested skill is alias-expanded (so "react" also matches a
        # stored "ReactJS") and normalized (so "React.js" and "react js"
        # match too), then OR'd across every alias of every requested
        # skill. A candidate matches if they have ANY of the comma-separated
        # skills, not all.
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        conditions = []
        for sk in skill_list:
            conditions.extend(_matches_any_alias(Candidate.resume_skills, sk, expand_skill))
        if conditions:
            query = query.where(or_(*conditions))
    if qualification:
        # education is stored per-resume on candidate_profiles, not on
        # candidates itself -- same correlated-subquery approach as
        # _qualification_condition() above (used by the plain search box),
        # kept as a subquery rather than a join so this composes safely with
        # every other filter active in the same request. Same normalized +
        # alias-expanded matching as everywhere else here -- this is what
        # makes "BSc" find a resume whose education field literally says
        # "Bachelor of Science".
        query = query.where(_qualification_condition(qualification.strip()))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/sectors/counts", response_model=list[SectorCount])
async def get_sector_counts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Powers the sector-cards landing page -- one row per sector that has
    at least one active candidate, with a live count. Unclassified
    candidates (sector is NULL -- still queued/failed extraction, or
    predate this feature) are intentionally excluded here rather than shown
    as a fake "Other" bucket; they still show up in the plain, unfiltered
    Candidates list."""
    query = (
        select(Candidate.sector, func.count(Candidate.id))
        .where(Candidate.deleted_at.is_(None), Candidate.sector.is_not(None))
        .group_by(Candidate.sector)
        .order_by(func.count(Candidate.id).desc())
    )
    result = await db.execute(query)
    return [SectorCount(sector=sector, count=count) for sector, count in result.all()]


# Per-candidate cap on how many matching lines search-resumes returns --
# bounds response size against a pathological resume that happens to repeat
# a common term a huge number of times. `has_more_matches` on the response
# tells the frontend when this was hit.
MAX_MATCHES_PER_CANDIDATE = 25
# Overall cap on how many candidates' worth of matches come back in one
# search-resumes response, newest-added first -- bounds response size (and
# the per-line scan below) as the candidate base grows. There's no index
# backing this search (a plain case-insensitive `contains` over
# candidate_profiles.raw_text), so it's an O(number of candidates) scan on
# the DB side too; fine at hundreds-to-low-thousands of resumes, worth
# revisiting (e.g. Postgres full-text search / pg_trgm) well before that.
MAX_SEARCH_RESULTS = 200


@router.get("/search-resumes", response_model=list[ResumeSearchResult])
async def search_resumes(
    q: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full-text search across every candidate's resume, not just the
    structured fields (skills/education/etc) the filters on GET /candidates
    search. Matches against CandidateProfile.raw_text -- the literal
    extracted text for a text-layer resume, or the GPT-5 vision
    transcription for a scanned one (see tasks_ingestion.py) -- so it finds
    anything actually written in the resume: a specific tool, a client name,
    a phrase, not just whatever GPT-5 chose to pull into the `skills` list.

    Returns one result per matching candidate, each with every matching
    line (up to MAX_MATCHES_PER_CANDIDATE) and the character-offset spans of
    the match within that line, so the frontend can highlight the exact
    match without re-implementing the matching logic client-side. Plain
    case-insensitive substring matching -- unlike the skills/qualification
    filters, this does NOT go through term_normalization.py's alias
    expansion (that's specifically for known degree/skill name variants;
    free-text resume search has no fixed vocabulary to expand against, and
    silently OR-ing in unrelated alias terms would make results harder to
    trust, not easier)."""
    term = q.strip()
    if not term:
        return []
    term_lower = term.lower()

    query = (
        select(Candidate, CandidateProfile.raw_text)
        .join(CandidateProfile, CandidateProfile.candidate_id == Candidate.id)
        .where(Candidate.deleted_at.is_(None))
        .where(func.lower(CandidateProfile.raw_text).contains(term_lower))
        .order_by(Candidate.added_on.desc())
        .limit(MAX_SEARCH_RESULTS)
    )
    rows = (await db.execute(query)).all()

    results: list[ResumeSearchResult] = []
    for candidate, raw_text in rows:
        matches: list[ResumeSearchMatch] = []
        truncated = False
        for line_number, line in enumerate((raw_text or "").splitlines(), start=1):
            line_lower = line.lower()
            offsets: list[list[int]] = []
            cursor = 0
            while True:
                idx = line_lower.find(term_lower, cursor)
                if idx == -1:
                    break
                offsets.append([idx, idx + len(term)])
                cursor = idx + len(term)
            if not offsets:
                continue
            if len(matches) >= MAX_MATCHES_PER_CANDIDATE:
                truncated = True
                break
            matches.append(ResumeSearchMatch(line_number=line_number, text=line, highlights=offsets))

        if not matches:
            # The DB-level `contains` above matched raw_text as a whole, but
            # the term happened to straddle a line break that splitlines()
            # then separated on -- rare, and there's no single line to show
            # a highlight in, so this candidate is skipped rather than
            # returned with an empty matches list.
            continue

        results.append(ResumeSearchResult(
            candidate_id=candidate.id,
            candidate_name=candidate.name,
            sector=candidate.sector,
            position_role=candidate.position_role,
            status=candidate.status,
            has_resume_file=bool(candidate.file_path),
            matches=matches,
            has_more_matches=truncated,
        ))

    return results


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate or candidate.deleted_at is not None:
        raise HTTPException(404, "Candidate not found")
    return candidate


@router.patch("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual override for fields the AI pipeline normally sets -- today
    just sector/position_role, for correcting a wrong or missing
    auto-classification from the Candidates directory UI. Once set here,
    tasks_ingestion.py's guarded-sync will never overwrite it on a later
    re-ingestion (it only fills currently-blank values)."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate or candidate.deleted_at is not None:
        raise HTTPException(404, "Candidate not found")

    data = payload.model_dump(exclude_unset=True)
    if "sector" in data and data["sector"] is not None:
        # VALID_SECTORS is the *suggested* list surfaced in the UI's
        # dropdown (and the only list GPT-5's own classification is allowed
        # to pick from -- see validation.py's _as_sector) -- but a human
        # correcting/creating a sector by hand is explicitly allowed to name
        # a sector that isn't in it yet (e.g. via SectorPicker's "+ Add a
        # new sector…"), since `sector` is a free-text column, not a DB
        # enum. Only basic sanity limits apply here: non-empty after
        # trimming, and within the column's String(50) size.
        data["sector"] = data["sector"].strip()
        if not data["sector"]:
            raise HTTPException(400, "sector cannot be blank -- omit the field instead to leave it unset")
        if len(data["sector"]) > 50:
            raise HTTPException(400, "sector must be 50 characters or fewer")

    for field, value in data.items():
        setattr(candidate, field, value)

    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.delete("/{candidate_id}", status_code=204)
async def delete_candidate(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Soft delete — candidate_profiles/embeddings/match_results/assessments
    all point at this row's id and stay intact (audit trail), matching the
    pattern in companies.py/jobs.py. The resume file on disk is left alone;
    it's tied to the id, not to whether the candidate record is 'active'."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate or candidate.deleted_at is not None:
        raise HTTPException(404, "Candidate not found")
    candidate.deleted_at = datetime.now(timezone.utc)
    await db.commit()


@router.get("/{candidate_id}/resume")
async def view_candidate_resume(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streams the candidate's resume file straight from disk (FileResponse
    streams in chunks, never loads the whole file into memory) so viewing a
    5,000-candidate directory's worth of resumes stays cheap regardless of
    how many exist."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    if not candidate.file_path:
        raise HTTPException(404, "No resume on file for this candidate")

    path = Path(candidate.file_path)
    if not path.exists():
        raise HTTPException(404, "Resume file is missing from storage")

    safe_name = candidate.name.strip().replace(" ", "_") or "resume"
    return FileResponse(path, filename=f"{safe_name}{path.suffix}")


@router.put("/{candidate_id}/resume", response_model=CandidateOut)
async def upload_candidate_resume(
    candidate_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attaches a resume to a candidate who doesn't have one yet, or
    replaces an existing one — the single place (besides bulk upload) that
    writes Candidate.file_path, so there's never more than one resume file
    on disk per candidate."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    contents = await file.read()
    new_path = _save_resume_file(candidate_id, file.filename, contents)

    # Replace, don't accumulate: remove the old file only after the new one
    # has been written successfully.
    _delete_resume_file(candidate.file_path)

    candidate.file_path = new_path
    candidate.status = "queued"  # same "needs (re)processing" state bulk upload sets
    await db.commit()
    await db.refresh(candidate)

    ingest_resume_task.delay(str(candidate.id), new_path)
    return candidate


@router.delete("/{candidate_id}/resume", response_model=CandidateOut)
async def delete_candidate_resume(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    _delete_resume_file(candidate.file_path)
    candidate.file_path = None
    await db.commit()
    await db.refresh(candidate)
    return candidate


@router.get("/{candidate_id}/profile")
async def get_candidate_profile(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Returns the AI-extracted profile if the ingestion pipeline has produced
    one yet; null fields otherwise (this is expected for most candidates
    right now, since the ATS pipeline doesn't require AI extraction to be
    usable — see placeholder_engine.py)."""
    profile = await db.get(CandidateProfile, candidate_id)
    if not profile:
        return None
    return {
        "candidate_id": str(profile.candidate_id),
        "skills": profile.skills,
        "work_history": profile.work_history,
        "education": profile.education,
        "certifications": profile.certifications,
        "total_experience_years": profile.total_experience_years,
    }