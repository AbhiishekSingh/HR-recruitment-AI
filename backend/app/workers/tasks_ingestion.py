import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.services.extraction.text_router import extract_text, ScannedPDFError
from app.services.extraction.vision_extractor import render_pdf_pages_to_base64_png
from app.services.llm.factory import get_llm_provider
from app.services.embeddings.factory import get_embedding_provider
from app.models.candidate import Candidate
from app.models.candidate_profile import CandidateProfile
from app.models.candidate_embedding import CandidateEmbedding


@celery_app.task(bind=True, max_retries=3)
def ingest_resume_task(self, candidate_id: str, file_path: str):
    """Runs the full ingestion pipeline for one resume: extract -> structure -> embed -> store.
    See project doc, Section 4.1."""
    try:
        asyncio.run(_ingest_resume(candidate_id, file_path))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            # Final attempt failed. Without this, the candidate is left
            # stuck at whatever in-progress status it last reached
            # ("extracting"/"embedding") forever, with nothing in the UI
            # telling the recruiter it's dead -- surface it as "failed"
            # instead so it's visible and actionable.
            asyncio.run(_mark_status(candidate_id, "failed"))
            raise
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


async def _mark_status(candidate_id: str, status: str) -> None:
    async with AsyncSessionLocal() as db:
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if candidate:
            candidate.status = status
            await db.commit()


async def _ingest_resume(candidate_id: str, file_path: str):
    async with AsyncSessionLocal() as db:
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            return

        candidate.status = "extracting"
        await db.commit()

        # 1. Extract raw text (non-LLM, cheap). A genuinely broken file
        # (corrupt, unsupported encoding, etc.) is not transient -- retrying
        # three times can't fix it, so mark it for manual review immediately
        # rather than burning retries and GPT-5 calls on a file that will
        # never parse. A *scanned* PDF (ScannedPDFError) isn't broken though
        # -- it just has no text layer to extract -- so that case falls
        # through to vision extraction below instead of needs_review.
        needs_vision = False
        try:
            raw_text = extract_text(file_path)
        except ScannedPDFError:
            needs_vision = True
            raw_text = None
        except Exception:
            candidate.status = "needs_review"
            await db.commit()
            return

        if not needs_vision and (not raw_text or not raw_text.strip()):
            candidate.status = "needs_review"
            await db.commit()
            return

        # 2. GPT-5 structured extraction.
        existing_profile = await db.get(CandidateProfile, candidate.id)

        if needs_vision:
            # No text layer, so there's nothing to dedup against before
            # paying for the call -- a scanned resume always re-runs GPT-5
            # vision on retry. Acceptable: scanned PDFs are the minority
            # case, and this keeps the fallback simple rather than caching
            # against an image hash for a rare path.
            try:
                llm = get_llm_provider()
                images = render_pdf_pages_to_base64_png(file_path)
                extraction = await llm.extract_resume_from_images(images)
            except Exception:
                candidate.status = "needs_review"
                await db.commit()
                return

            # No literal extracted text exists for a scanned PDF -- store a
            # short synthesized summary instead so raw_text still has
            # something usable for display/dedup bookkeeping elsewhere.
            raw_text = _build_embedding_summary(extraction)
            contact = _extract_contact_fields(extraction)
            profile = CandidateProfile(
                candidate_id=candidate.id,
                raw_text=raw_text,
                skills=extraction.get("skills", []),
                work_history=extraction.get("work_history", []),
                education=extraction.get("education", []),
                certifications=extraction.get("certifications", []),
                total_experience_years=extraction.get("total_experience_years"),
                extraction_model_version=llm.extraction_model,
            )
            await db.merge(profile)
        elif existing_profile and existing_profile.raw_text == raw_text:
            # Skipped because a profile already exists for this exact resume
            # text -- this is what makes a Celery retry after a step-3
            # (embedding) failure cheap: without this check, every retry
            # re-pays for the GPT-5 extraction call even though it already
            # succeeded the first time.
            extraction = {
                "skills": existing_profile.skills,
                "work_history": existing_profile.work_history,
                "education": existing_profile.education,
                "certifications": existing_profile.certifications,
                "total_experience_years": existing_profile.total_experience_years,
            }
            # Re-run (cached path), extracted contact fields aren't stored on
            # the profile -- re-derive them from raw_text isn't worth a
            # second LLM call here, so this path just skips the Candidate
            # sync below (it will already have been synced the first time
            # this resume was extracted).
            contact = {}
        else:
            llm = get_llm_provider()
            extraction = await llm.extract_resume(raw_text)
            contact = _extract_contact_fields(extraction)

            profile = CandidateProfile(
                candidate_id=candidate.id,
                raw_text=raw_text,
                skills=extraction.get("skills", []),
                work_history=extraction.get("work_history", []),
                education=extraction.get("education", []),
                certifications=extraction.get("certifications", []),
                total_experience_years=extraction.get("total_experience_years"),
                extraction_model_version=llm.extraction_model,
            )
            await db.merge(profile)

        # Sync extracted identity/experience onto the Candidate row so the
        # pipeline table shows real resume data instead of the placeholder
        # values set at bulk-upload time (filename-guessed name, a
        # "<uuid>@pending.local" stand-in email, experience_years=0).
        # Guarded so this never clobbers a candidate who was added through
        # the manual "Add Candidate" form with real details already filled
        # in -- only bulk-upload placeholders get overwritten:
        #   - email: only if it's still the "@pending.local" placeholder
        #     AND the resume actually yielded a non-empty email.
        #   - name: only if it still looks like the filename-derived
        #     placeholder (no real name was ever entered) AND extraction
        #     produced a non-empty name.
        #   - phone/current_company: only fill if currently blank.
        #   - experience_years: only overwrite if currently 0 (unset) and
        #     extraction produced a real number.
        # A "@pending.local" email is the reliable signal that this
        # candidate was created by bulk upload with no real details typed
        # in (see candidates.py's bulk-upload endpoint) -- it's what makes
        # it safe to overwrite name/email together without touching a
        # candidate who came from the manual "Add Candidate" form.
        is_placeholder_candidate = candidate.email.endswith("@pending.local")
        if is_placeholder_candidate:
            if contact.get("candidate_email"):
                candidate.email = contact["candidate_email"]
            if contact.get("candidate_name"):
                candidate.name = contact["candidate_name"]
        if contact.get("candidate_phone") and not candidate.phone:
            candidate.phone = contact["candidate_phone"]
        if contact.get("current_company") and not candidate.current_company:
            candidate.current_company = contact["current_company"]
        exp_years = extraction.get("total_experience_years")
        if exp_years and not candidate.experience_years:
            candidate.experience_years = exp_years

        candidate.status = "embedding"
        await db.commit()

        # 3. Build a clean summary and embed it (see doc: extract-then-embed, not RAG chunking)
        summary = _build_embedding_summary(extraction)
        embedder = get_embedding_provider()
        vectors = await embedder.embed([summary])

        embedding_row = CandidateEmbedding(
            candidate_id=candidate.id,
            embedding=vectors[0],
            embedding_model_version=embedder.model_version,
        )
        await db.merge(embedding_row)

        candidate.status = "ready"
        await db.commit()


def _extract_contact_fields(extraction: dict) -> dict:
    return {
        "candidate_name": extraction.get("candidate_name", ""),
        "candidate_email": extraction.get("candidate_email", ""),
        "candidate_phone": extraction.get("candidate_phone", ""),
        "current_company": extraction.get("current_company", ""),
    }


def _build_embedding_summary(extraction: dict) -> str:
    skills = ", ".join(extraction.get("skills", []))
    roles = "; ".join(
        f"{w.get('role', '')} at {w.get('company', '')}: {', '.join(w.get('achievements', []))}"
        for w in extraction.get("work_history", [])
    )
    return f"Skills: {skills}\nExperience: {roles}"
