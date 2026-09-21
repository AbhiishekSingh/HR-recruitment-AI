import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.api.deps import get_db, get_current_user
from app.config import settings
from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.assessment import Assessment
from app.models.job_posting import JobPosting
from app.models.user import User
from app.schemas.candidate import CandidateCreate, CandidateOut
from app.workers.tasks_ingestion import ingest_resume_task

router = APIRouter()

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
    existing = await db.execute(select(Candidate).where(Candidate.email == payload.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "A candidate with this email already exists")

    candidate = Candidate(**payload.model_dump(), email=payload.email.lower(), status="ready")
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Candidate).order_by(Candidate.added_on.desc())
    if search:
        q = f"%{search.lower()}%"
        query = query.where(or_(Candidate.name.ilike(q), Candidate.email.ilike(q), Candidate.phone.ilike(q)))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


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