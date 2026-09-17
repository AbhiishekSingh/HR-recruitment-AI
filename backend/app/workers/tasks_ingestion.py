import asyncio
import uuid

from app.workers.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.services.extraction.text_router import extract_text
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
        # Idempotent retry: re-running does not duplicate rows (upsert-style writes below)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


async def _ingest_resume(candidate_id: str, file_path: str):
    async with AsyncSessionLocal() as db:
        candidate = await db.get(Candidate, uuid.UUID(candidate_id))
        if not candidate:
            return

        candidate.status = "extracting"
        await db.commit()

        # 1. Extract raw text (non-LLM, cheap)
        raw_text = extract_text(file_path)

        # 2. GPT-5 structured extraction
        llm = get_llm_provider()
        extraction = await llm.extract_resume(raw_text)

        profile = CandidateProfile(
            candidate_id=candidate.id,
            raw_text=raw_text,
            skills=extraction.get("skills", []),
            work_history=extraction.get("work_history", []),
            education=extraction.get("education", []),
            certifications=extraction.get("certifications", []),
            total_experience_years=extraction.get("total_experience_years"),
            extraction_model_version=llm.model,
        )
        await db.merge(profile)

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


def _build_embedding_summary(extraction: dict) -> str:
    skills = ", ".join(extraction.get("skills", []))
    roles = "; ".join(
        f"{w.get('role', '')} at {w.get('company', '')}: {', '.join(w.get('achievements', []))}"
        for w in extraction.get("work_history", [])
    )
    return f"Skills: {skills}\nExperience: {roles}"
