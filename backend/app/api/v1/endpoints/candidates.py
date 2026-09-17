import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
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

    # candidate = Candidate(**payload.model_dump(), email=payload.email.lower(), status="ready")
    data = payload.model_dump()
    data["email"] = data["email"].lower()
    candidate = Candidate(**data, status="ready")
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
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        ext = Path(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"Unsupported file type: {file.filename}")

        candidate_id = uuid.uuid4()
        dest_path = upload_dir / f"{candidate_id}{ext}"
        contents = await file.read()
        dest_path.write_bytes(contents)

        guessed_name = Path(file.filename).stem.replace("_", " ").replace("-", " ").title()
        candidate = Candidate(
            id=candidate_id, name=guessed_name, email=f"{candidate_id}@pending.local",
            file_path=str(dest_path), status="queued",
        )
        db.add(candidate)
        await db.flush()

        if job_id:
            db.add(Assessment(candidate_id=candidate.id, job_id=job_id, final_status="Pending Screening", screened=False))

        await db.commit()
        await db.refresh(candidate)

        ingest_resume_task.delay(str(candidate.id), str(dest_path))
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
