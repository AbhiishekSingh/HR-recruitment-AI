import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.models.job_posting import JobPosting
from app.models.company import Company
from app.models.user import User
from app.schemas.job import (
    JobPostingCreate, JobPostingOut, JobStatusUpdate, JobPostingUpdate,
    JDParseResult, JDFormFields, JDAttachResult,
)
from app.services import jd_files, ai_usage
from app.services.scoring.job_config import must_skills, nice_skills, sanitize_config, sanitize_groups
from app.workers.tasks_matching import embed_job_task

router = APIRouter()


@router.post("", response_model=JobPostingOut)
async def create_job(
    payload: JobPostingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = await db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    data = payload.model_dump(exclude={"jd_upload_token", "requirements", "skill_groups", "related_titles"})
    job = JobPosting(**data, created_by=current_user.id, requirements=payload.requirements or {}, scoring_config={})
    _apply_scoring_settings(
        job,
        [g.model_dump() for g in payload.skill_groups] if payload.skill_groups is not None else None,
        payload.related_titles,
    )
    db.add(job)
    await db.flush()  # assigns job.id for the JD file name

    if payload.jd_upload_token:
        pending = jd_files.find_pending(payload.jd_upload_token)
        if pending is None:
            raise HTTPException(400, "The uploaded JD file has expired. Please upload it again")
        stored = jd_files.store_for_job(job.id, pending)
        job.jd_file_path = str(stored)
        job.jd_file_name = _original_name(payload.jd_upload_token, stored)

    await db.commit()
    await db.refresh(job)
    _queue_job_embedding(job.id)
    return job


def _apply_scoring_settings(job: JobPosting, groups: list[dict] | None, related_titles: list[str] | None) -> None:
    """Saves skill groups / related titles and keeps the older fields in step:
    required_skills = all must-have skills, requirements.nice_to_have_skills
    = all nice-to-have skills (AI matching and the skill chips use those)."""
    if groups is None and related_titles is None:
        return
    current = sanitize_config(job.scoring_config or {})
    if groups is not None:
        current["skill_groups"] = sanitize_groups(groups)
    if related_titles is not None:
        current["related_titles"] = sanitize_config({"related_titles": related_titles})["related_titles"]
    job.scoring_config = current
    if groups is not None and current["skill_groups"]:
        musts = must_skills(current["skill_groups"])
        if musts:
            job.required_skills = musts
        req = dict(job.requirements or {})
        req["required_skills"] = musts or req.get("required_skills", [])
        req["nice_to_have_skills"] = nice_skills(current["skill_groups"])
        job.requirements = req


def _queue_job_embedding(job_id) -> None:
    """(Re)builds the job's "meaning match" embedding in the background
    (about ₹0.001). Never blocks the request."""
    try:
        embed_job_task.delay(str(job_id))
    except Exception:
        pass  # Celery/Redis down: the meaning match is just left out until next save


# Original file names of pending JD uploads (token -> name), so the stored
# file can keep a friendly download name. In-memory is fine: a lost entry
# only means the download is named "<job title>.pdf" instead.
_pending_names: dict[str, str] = {}


def _original_name(token: str, stored: Path) -> str:
    return _pending_names.pop(token, None) or f"JD{stored.suffix}"


async def _parse_upload(file: UploadFile) -> tuple[bytes, str]:
    contents = await file.read()
    name = file.filename or "jd"
    problem = jd_files.jd_file_problem(name, len(contents))
    if problem:
        raise HTTPException(400, problem)
    return contents, name


async def _read_into_result(path: Path, file_name: str, token: str | None) -> JDParseResult:
    raw_text, fields, error = await jd_files.read_jd(path)
    return JDParseResult(
        upload_token=token,
        file_name=file_name,
        fields=JDFormFields(**(fields or {})) if fields else JDFormFields(),
        missing=jd_files.missing_fields(fields),
        requirements=jd_files.requirements_from(fields),
        raw_text=raw_text,
        error=error,
    )


@router.post("/parse-jd", response_model=JDParseResult)
async def parse_jd_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Step 1 of "+ New requisition" with a JD file: saves the file and
    reads it with AI so the form can be pre-filled. Nothing is created
    until HR clicks Create (POST /jobs with the returned upload_token).
    If the AI can't read the file, `error` explains why and the form is
    filled manually -- the file is still attached on create."""
    contents, name = await _parse_upload(file)
    token, path = jd_files.save_pending(name, contents)
    _pending_names[token] = name[:300]
    return await _read_into_result(path, name, token)


@router.get("", response_model=list[JobPostingOut])
async def list_jobs(
    company_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(JobPosting).where(JobPosting.deleted_at.is_(None)).order_by(JobPosting.opened_on.desc())
    if company_id:
        query = query.where(JobPosting.company_id == company_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobPostingOut)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")
    return job


@router.patch("/{job_id}", response_model=JobPostingOut)
async def update_job(
    job_id: uuid.UUID,
    payload: JobPostingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a requisition (used by "Update job from this JD")."""
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")
    data = payload.model_dump(exclude_unset=True)
    groups = data.pop("skill_groups", None)
    related = data.pop("related_titles", None)
    if "title" in data and not (data["title"] or "").strip():
        raise HTTPException(400, "Role title cannot be blank")
    new_requirements = data.pop("requirements", None)
    for field, value in data.items():
        if value is not None:
            setattr(job, field, value)
    if new_requirements is not None:
        # merge, so editing fields never drops responsibilities etc.
        job.requirements = {**(job.requirements or {}), **new_requirements}
    _apply_scoring_settings(job, groups, related)
    rescore_inputs = {"required_skills", "raw_text", "title"}
    re_embed = bool(rescore_inputs & set(data)) or new_requirements is not None or groups is not None or related is not None
    if re_embed:
        job.embedding = None
    await db.commit()
    await db.refresh(job)
    if re_embed:
        _queue_job_embedding(job.id)
    return job


@router.get("/{job_id}/jd")
async def view_jd_file(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streams the original JD file, same pattern as a candidate's resume."""
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")
    if not job.jd_file_path:
        raise HTTPException(404, "No JD file on file for this job")
    path = Path(job.jd_file_path)
    if not path.exists():
        raise HTTPException(404, "JD file is missing from storage")
    name = job.jd_file_name or f"{job.title.strip().replace(' ', '_') or 'JD'}{path.suffix}"
    return FileResponse(path, filename=name)


@router.put("/{job_id}/jd", response_model=JDAttachResult)
async def attach_jd_file(
    job_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attaches (or replaces) the JD file of an existing job. The file is
    saved straight away; `parse` carries the values read from it, which
    the frontend offers as "Update job fields from this JD" -- the job's
    fields only change if HR saves that (PATCH /jobs/{id})."""
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")
    contents, name = await _parse_upload(file)
    _, pending = jd_files.save_pending(name, contents)
    stored = jd_files.store_for_job(job.id, pending)
    job.jd_file_path = str(stored)
    job.jd_file_name = name[:300]
    await db.commit()
    await db.refresh(job)
    with ai_usage.usage_context(job_id=job.id):
        parse = await _read_into_result(stored, name, None)
    return JDAttachResult(job=job, parse=parse)


@router.patch("/{job_id}/status", response_model=JobPostingOut)
async def set_job_status(
    job_id: uuid.UUID,
    payload: JobStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """JD Active/Inactive toggle. Stored in the existing `status` column
    ("Open" = Active, "Closed" = Inactive) so nothing else that reads
    job.status has to change. Label only -- nothing is blocked."""
    if payload.status not in ("Open", "Closed"):
        raise HTTPException(400, "status must be 'Open' (Active) or 'Closed' (Inactive)")
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")
    job.status = payload.status
    await db.commit()
    await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Soft delete — see companies.delete_company for why. A closed job uses
    `status = 'Closed'`; this is only for 'this requisition shouldn't have
    existed', keeping match_results/assessments tied to it intact for audit."""
    job = await db.get(JobPosting, job_id)
    if not job or job.deleted_at is not None:
        raise HTTPException(404, "Job posting not found")
    job.deleted_at = datetime.now(timezone.utc)
    await db.commit()
