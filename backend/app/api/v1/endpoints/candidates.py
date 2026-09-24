import logging
import tempfile
import uuid
from datetime import datetime, timezone
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
from app.services.extraction.text_router import extract_text, ScannedPDFError
from app.services.extraction.vision_extractor import render_pdf_pages_to_base64_png
from app.services.llm.factory import get_llm_provider
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


@router.post("/parse-resume")
async def parse_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Reads one resume file and returns extracted fields to prefill the
    'Add candidate' form -- nothing is written to the database here. The
    file itself is re-uploaded separately when the form is actually saved
    (create_candidate doesn't accept a file, so the frontend attaches it
    via PUT /{candidate_id}/resume right after creating the record).

    Runs the same extract_text -> GPT-5 extract_resume steps as the
    ingestion pipeline, just synchronously and without Celery -- one file,
    one request, the person is watching the form and waiting on it, so a
    background task queue would only add latency here, not value.

    A parse failure (corrupt file, no text layer, GPT-5 error) degrades to
    an empty/best-effort result rather than a 500: the person can still
    fill the form in by hand, this is a convenience, not a requirement."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {file.filename}")

    contents = await file.read()
    if len(contents) > MAX_RESUME_BYTES:
        raise HTTPException(400, f"{file.filename} exceeds the 5MB resume size limit")

    empty_result = {
        "candidate_name": "", "candidate_email": "", "candidate_phone": "",
        "current_company": "", "skills": [], "total_experience_years": None,
        "resume_summary": "", "warning": None,
    }

    # extract_text/render_pdf_pages_to_base64_png need a real path on disk,
    # not the bytes -- write to a throwaway temp file rather than a
    # candidate's permanent upload slot, since no candidate exists yet at
    # this point.
    with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
        tmp.write(contents)
        tmp.flush()

        try:
            raw_text = extract_text(tmp.name)
        except ScannedPDFError:
            # No text layer -- fall back to GPT-5 vision reading the page
            # images directly, instead of requiring Tesseract/Poppler.
            try:
                llm = get_llm_provider()
                images = render_pdf_pages_to_base64_png(tmp.name)
                extraction = await llm.extract_resume_from_images(images)
            except Exception:
                logger.exception("parse_resume: vision extraction failed for %s", file.filename)
                return {**empty_result, "warning": "Couldn't read this scanned PDF automatically -- fill in the details manually."}
            return _parsed_response(extraction, resume_summary=_summarize_extraction(extraction))
        except Exception:
            # Logged with the traceback rather than swallowed silently --
            # this used to be a black hole where "couldn't read text" could
            # mean several different things. Check the server/worker logs
            # for this line to see the real cause.
            logger.exception("parse_resume: extract_text failed for %s", file.filename)
            return {**empty_result, "warning": "Couldn't read text from this file -- fill in the details manually."}

    if not raw_text or not raw_text.strip():
        return {**empty_result, "warning": "Couldn't read text from this file -- fill in the details manually."}

    try:
        llm = get_llm_provider()
        extraction = await llm.extract_resume(raw_text)
    except Exception:
        logger.exception("parse_resume: llm.extract_resume failed for %s", file.filename)
        return {**empty_result, "warning": "Automatic parsing failed -- fill in the details manually."}

    return _parsed_response(extraction, resume_summary=raw_text.strip()[:600])


def _parsed_response(extraction: dict, resume_summary: str) -> dict:
    return {
        "candidate_name": extraction.get("candidate_name", ""),
        "candidate_email": extraction.get("candidate_email", ""),
        "candidate_phone": extraction.get("candidate_phone", ""),
        "current_company": extraction.get("current_company", ""),
        "skills": extraction.get("skills", []),
        "total_experience_years": extraction.get("total_experience_years"),
        "resume_summary": resume_summary,
        "warning": None,
    }


def _summarize_extraction(extraction: dict) -> str:
    """Builds a short human-readable summary from structured extraction --
    used in place of raw text when the resume came from vision extraction
    (a scanned PDF never has extracted text to slice a summary from)."""
    skills = ", ".join(extraction.get("skills", [])[:10])
    roles = "; ".join(
        f"{w.get('role', '')} at {w.get('company', '')}"
        for w in extraction.get("work_history", [])[:3]
    )
    return f"Skills: {skills}\nExperience: {roles}"[:600]


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
    query = select(Candidate).where(Candidate.deleted_at.is_(None)).order_by(Candidate.added_on.desc())
    if search:
        q = f"%{search.lower()}%"
        query = query.where(or_(Candidate.name.ilike(q), Candidate.email.ilike(q), Candidate.phone.ilike(q)))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate or candidate.deleted_at is not None:
        raise HTTPException(404, "Candidate not found")
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