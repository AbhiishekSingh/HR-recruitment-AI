"""Job-description (JD) file handling for requisitions.

Flow for "+ New requisition":
  1. POST /jobs/parse-jd  -> the file is saved under uploads/jds/pending/
     with a random token, read, and run through the AI once; the form gets
     pre-fill values + the token.
  2. POST /jobs (with jd_upload_token) -> the pending file is moved to
     uploads/jds/<job_id>.<ext> and linked to the new job.
A pending file whose form was never saved is just left in pending/ (it is
never linked to anything); clear_old_pending() removes ones older than a day.
"""
import logging
import secrets
import time
from pathlib import Path

from app.config import settings
from app.services.extraction.text_router import extract_text, ScannedPDFError
from app.services.extraction.vision_extractor import render_pdf_pages_to_base64_png
from app.services.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

ALLOWED_JD_EXTENSIONS = {".pdf", ".docx"}
MAX_JD_MB = 4
MAX_JD_BYTES = MAX_JD_MB * 1024 * 1024
PENDING_MAX_AGE_SECONDS = 24 * 3600

# Form field -> label, for "not found in JD" highlighting.
FORM_FIELDS = {
    "title": "Role title",
    "locations": "Locations",
    "budget_min": "Budget min",
    "budget_max": "Budget max",
    "experience_min": "Experience min",
    "experience_max": "Experience max",
    "max_notice_days": "Max notice period",
    "required_skills": "Required skills",
}


def jd_dir() -> Path:
    path = Path(settings.upload_dir) / "jds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pending_dir() -> Path:
    path = jd_dir() / "pending"
    path.mkdir(parents=True, exist_ok=True)
    return path


def jd_file_problem(filename: str, size: int) -> str | None:
    ext = Path(filename or "").suffix.lower()
    if ext == ".doc":
        return "Old Word format (.doc) is not supported. Save it as .docx or PDF"
    if ext not in ALLOWED_JD_EXTENSIONS:
        return f"Unsupported file type ({ext or 'no extension'}). Upload the JD as PDF or Word (.docx)"
    if size == 0:
        return "File is empty"
    if size > MAX_JD_BYTES:
        return f"File is {size / (1024 * 1024):.1f}MB; the limit is {MAX_JD_MB}MB"
    return None


def clear_old_pending() -> None:
    cutoff = time.time() - PENDING_MAX_AGE_SECONDS
    for f in pending_dir().glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def save_pending(filename: str, contents: bytes) -> tuple[str, Path]:
    """Saves an uploaded JD before its job exists. Returns (token, path)."""
    clear_old_pending()
    ext = Path(filename).suffix.lower()
    token = secrets.token_hex(16)
    path = pending_dir() / f"{token}{ext}"
    path.write_bytes(contents)
    return token, path


def find_pending(token: str) -> Path | None:
    if not token or not token.isalnum() or len(token) > 64:
        return None  # never let a token reach the filesystem as a path
    matches = [p for p in pending_dir().glob(f"{token}.*") if p.suffix.lower() in ALLOWED_JD_EXTENSIONS]
    return matches[0] if matches else None


def store_for_job(job_id, source: Path) -> Path:
    """Moves/copies a JD file to its permanent place for this job, replacing
    any previous JD file of that job."""
    for old in jd_dir().glob(f"{job_id}.*"):
        if old.is_file():
            old.unlink()
    dest = jd_dir() / f"{job_id}{source.suffix.lower()}"
    source.replace(dest)
    return dest


async def read_jd(path: Path) -> tuple[str, dict | None, str | None]:
    """Returns (raw_text, form_fields or None, error message or None).
    Never raises: if the AI can't read the file, HR fills the form by hand
    and the file is still attached."""
    raw_text = ""
    images: list[str] | None = None
    try:
        raw_text = extract_text(str(path))
    except ScannedPDFError:
        try:
            images = render_pdf_pages_to_base64_png(str(path))
        except Exception:
            logger.exception("Could not render JD pages %s", path)
            return "", None, "Could not read this file (it may be corrupt or password-protected)"
    except Exception:
        logger.exception("Could not extract JD text %s", path)
        return "", None, "Could not read this file (it may be corrupt or password-protected)"

    if images is None and not raw_text.strip():
        return "", None, "No readable text found in this file"

    llm = get_llm_provider()
    try:
        if images is not None:
            fields = await llm.extract_jd_form_from_images(images)
        else:
            fields = await llm.extract_jd_form(raw_text[:30000])
        return raw_text, fields, None
    except NotImplementedError as exc:
        return raw_text, None, str(exc)
    except Exception as exc:
        logger.exception("JD AI extraction failed for %s", path)
        return raw_text, None, f"AI could not read the JD ({type(exc).__name__}). Please fill the form manually"
    finally:
        try:
            await llm.aclose()
        except Exception:
            pass


def missing_fields(fields: dict | None) -> list[str]:
    """Form fields the JD didn't provide (HR must fill them)."""
    if not fields:
        return list(FORM_FIELDS.keys())
    out = []
    for key in FORM_FIELDS:
        value = fields.get(key)
        if value is None or value == [] or value == "":
            out.append(key)
    return out


def requirements_from(fields: dict | None) -> dict:
    """Same shape as coerce_jd_extraction(), stored on JobPosting.requirements
    so AI matching can use it without extracting the JD again."""
    if not fields:
        return {}
    return {
        "required_skills": fields.get("required_skills", []),
        "nice_to_have_skills": fields.get("nice_to_have_skills", []),
        "min_experience_years": fields.get("experience_min"),
        "responsibilities": fields.get("responsibilities", []),
        "qualifications": fields.get("qualifications", []),
        "hard_requirements": fields.get("hard_requirements", []),
    }


def scoring_config_from(fields: dict | None) -> dict:
    """Skill groups + related titles suggested by the AI from the JD."""
    if not fields:
        return {}
    return {"skill_groups": fields.get("skill_groups", []), "related_titles": fields.get("related_titles", [])}
