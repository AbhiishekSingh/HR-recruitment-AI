import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.config import settings
from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.user import User
from app.schemas.candidate import CandidateOut, CandidateProfileOut
from app.workers.tasks_ingestion import ingest_resume_task

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@router.post("/upload", response_model=list[CandidateOut])
async def upload_resumes(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk resume upload. Saves each file locally and enqueues an ingestion job per resume."""
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

        candidate = Candidate(id=candidate_id, file_path=str(dest_path), status="queued")
        db.add(candidate)
        await db.commit()
        await db.refresh(candidate)

        ingest_resume_task.delay(str(candidate.id), str(dest_path))
        created.append(candidate)

    return created


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate


@router.get("/{candidate_id}/profile", response_model=CandidateProfileOut)
async def get_candidate_profile(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(CandidateProfile, candidate_id)
    if not profile:
        raise HTTPException(404, "Profile not found (candidate may still be processing)")
    return profile


@router.get("", response_model=list[CandidateOut])
async def list_candidates(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Candidate))
    return result.scalars().all()
