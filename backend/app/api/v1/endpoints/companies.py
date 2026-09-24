import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_user
from app.config import settings
from app.models.company import Company
from app.models.user import User
from app.schemas.company import CompanyOut

router = APIRouter()

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024  # 5MB, enforced server-side (never trust the browser alone)


def _save_company_document(company_id: uuid.UUID, filename: str, contents: bytes) -> str:
    """Validates and writes one company document to disk, returning the
    stored path -- same pattern as candidates._save_resume_file, kept
    separate since companies live in their own upload subdirectory."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {filename} -- upload a PDF or Word document")
    if len(contents) > MAX_DOCUMENT_BYTES:
        raise HTTPException(400, f"{filename} exceeds the 5MB document size limit")

    upload_dir = Path(settings.upload_dir) / "companies"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest_path = upload_dir / f"{company_id}{ext}"
    dest_path.write_bytes(contents)
    return str(dest_path)


def _delete_company_document(document_path: str | None) -> None:
    """Removes a company document from disk if it exists. Never raises --
    a missing file on disk shouldn't block the database update."""
    if not document_path:
        return
    path = Path(document_path)
    if path.exists():
        path.unlink()


@router.post("", response_model=CompanyOut)
async def create_company(
    name: str = Form(...),
    industry: str = Form(""),
    contact_name: str = Form(""),
    contact_email: str = Form(""),
    gst_number: str = Form(""),
    tier: str = Form("Standard"),
    document: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Onboards a company. Multipart rather than JSON so the optional
    supporting document (registration certificate, agreement, etc. -- PDF
    or Word) rides along in the same request as the rest of the form,
    instead of a separate create-then-upload round trip."""
    company = Company(
        name=name,
        industry=industry,
        contact_name=contact_name,
        contact_email=contact_email,
        gst_number=gst_number,
        tier=tier,
    )
    db.add(company)
    await db.flush()  # assigns company.id before we need it for the filename

    if document is not None and document.filename:
        contents = await document.read()
        if contents:
            company.document_path = _save_company_document(company.id, document.filename, contents)

    await db.commit()
    await db.refresh(company)
    return company


@router.get("", response_model=list[CompanyOut])
async def list_companies(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Company).where(Company.deleted_at.is_(None)).order_by(Company.onboarded_on.desc())
    )
    return result.scalars().all()


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    company = await db.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/{company_id}/document")
async def view_company_document(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Streams the company's uploaded document straight from disk, same as
    GET /candidates/{id}/resume."""
    company = await db.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise HTTPException(404, "Company not found")
    if not company.document_path:
        raise HTTPException(404, "No document on file for this company")

    path = Path(company.document_path)
    if not path.exists():
        raise HTTPException(404, "Document file is missing from storage")

    safe_name = company.name.strip().replace(" ", "_") or "company_document"
    return FileResponse(path, filename=f"{safe_name}{path.suffix}")


@router.put("/{company_id}/document", response_model=CompanyOut)
async def upload_company_document(
    company_id: uuid.UUID,
    document: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attaches a document to a company that doesn't have one yet, or
    replaces the existing one."""
    company = await db.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise HTTPException(404, "Company not found")

    contents = await document.read()
    new_path = _save_company_document(company_id, document.filename, contents)

    # Replace, don't accumulate: remove the old file only after the new one
    # has been written successfully.
    _delete_company_document(company.document_path)

    company.document_path = new_path
    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=204)
async def delete_company(company_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Soft delete only — a company row is the anchor for its jobs, and jobs
    are the anchor for match_results/assessments, so a hard delete would
    either cascade-destroy the agency's whole history for that client or
    orphan foreign keys. deleted_at hides it from list/get; nothing else
    changes, so historical jobs/assessments tied to it stay intact."""
    company = await db.get(Company, company_id)
    if not company or company.deleted_at is not None:
        raise HTTPException(404, "Company not found")
    company.deleted_at = datetime.now(timezone.utc)
    await db.commit()
