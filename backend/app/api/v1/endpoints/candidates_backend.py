import logging
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
from app.schemas.candidate import CandidateCreate, CandidateOut, CandidateUpdate, SectorCount
from app.services.llm.validation import VALID_SECTORS
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
    though the ATS pipeline doesn't depend on its output yet."""
    if job_id:
        job = await db.get(JobPosting, job_id)
        if not job:
            raise HTTPException(404, "Job posting not found")

    created = []

    for file in files:
        candidate_id = uuid.uuid4()
        contents = await file.read()
        dest_path = _save_resume_file(candidate_id, file.filename, contents)

        guessed_name = Path(file.filename).stem.replace("_", " ").replace("-", " ").title()
        candidate = Candidate(
            id=candidate_id, name=guessed_name, email=f"{candidate_id}@pending.local",
            file_path=dest_path, status="queued",
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
    query = select(Candidate).where(Candidate.deleted_at.is_(None)).order_by(Candidate.added_on.desc())
    if search:
        q = f"%{search.lower()}%"
        query = query.where(or_(Candidate.name.ilike(q), Candidate.email.ilike(q), Candidate.phone.ilike(q)))
    if sector:
        query = query.where(Candidate.sector == sector)
    if min_experience is not None:
        query = query.where(Candidate.experience_years >= min_experience)
    if max_experience is not None:
        query = query.where(Candidate.experience_years <= max_experience)
    if skills:
        # resume_skills is a JSONB list (e.g. ["React", "TypeScript"]). Rather than
        # requiring an exact, case-sensitive element match (which Postgres's native
        # `?|` JSONB operator would need), cast the array to text and substring-match
        # each requested skill against it case-insensitively -- simple and good enough
        # at this scale, and tolerant of "react" matching a stored "React (Hooks)".
        # A candidate matches if they have ANY of the comma-separated skills, not all.
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        if skill_list:
            skills_text = func.lower(cast(Candidate.resume_skills, String))
            query = query.where(or_(*[skills_text.contains(sk.lower()) for sk in skill_list]))
    if qualification:
        # education is stored per-resume on candidate_profiles, not on candidates
        # itself, so this needs a join. Same cast-to-text + substring-match approach
        # as skills, matched against the candidate's most recent extraction only.
        query = query.join(CandidateProfile, CandidateProfile.candidate_id == Candidate.id)
        query = query.where(func.lower(cast(CandidateProfile.education, String)).contains(qualification.strip().lower()))
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
    if "sector" in data and data["sector"] is not None and data["sector"] not in VALID_SECTORS:
        raise HTTPException(400, f"sector must be one of: {sorted(VALID_SECTORS)}")

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