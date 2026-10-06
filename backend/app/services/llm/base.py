from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstraction so the reasoning model (GPT-5 today) can be swapped later
    without touching extraction/scoring business logic elsewhere in the app."""

    @abstractmethod
    async def extract_jd(self, jd_text: str) -> dict:
        """Returns a dict matching schemas.job.JDExtractionResult."""
        raise NotImplementedError

    @abstractmethod
    async def extract_resume(self, resume_text: str) -> dict:
        """Returns a dict matching schemas.candidate.ResumeExtractionResult."""
        raise NotImplementedError

    @abstractmethod
    async def extract_resume_from_images(self, images_b64: list[str]) -> dict:
        """Same shape as extract_resume, but for a scanned/image-only PDF
        with no text layer -- reads the page images directly via a
        vision-capable model instead of requiring a separate OCR engine."""
        raise NotImplementedError

    async def transcribe_resume_images(self, images_b64: list[str]) -> str:
        """Verbatim line-by-line text transcription of a scanned/image-only
        resume's pages, for full-text search (see prompts/resume_extraction
        .py's build_resume_transcription_prompt). Not abstract: a provider
        that can't do this (or where it isn't worth the extra call) can fall
        back to the default no-op below, and callers treat an empty string
        the same as "not available" -- see tasks_ingestion.py."""
        return ""

    async def extract_jd_form(self, jd_text: str) -> dict:
        """JD text -> requisition-form pre-fill values (see
        validation.coerce_jd_form_extraction). Not abstract so other
        providers keep working; they just can't pre-fill from a JD file."""
        raise NotImplementedError("This AI provider can't read JD files")

    async def extract_jd_form_from_images(self, images_b64: list[str]) -> dict:
        """Same as extract_jd_form, for a scanned/image-only JD PDF."""
        raise NotImplementedError("This AI provider can't read scanned JD files")

    @abstractmethod
    async def score_candidate(self, jd_requirements: dict, candidate_profile: dict) -> dict:
        """Returns a dict matching schemas.match.MatchResultOut (score/matched/missing/etc)."""
        raise NotImplementedError

    async def aclose(self) -> None:
        """Releases the provider's underlying HTTP client/connections.
        Default no-op for providers that don't hold one; concrete providers
        backed by an async HTTP client (e.g. AsyncOpenAI) MUST override this.
        Callers running inside a per-call `asyncio.run(...)` (see
        tasks_ingestion.py) must await this before that call returns -- an
        unclosed async client's connections outlive the event loop they were
        opened on, and Python's later garbage-collection attempt to close
        them then raises "RuntimeError: Event loop is closed" and, worse on
        Windows' ProactorEventLoop, can leave the *next* asyncio.run() call
        in the same worker process in a broken state."""
        return None
