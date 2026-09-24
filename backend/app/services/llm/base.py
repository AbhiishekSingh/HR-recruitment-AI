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

    @abstractmethod
    async def score_candidate(self, jd_requirements: dict, candidate_profile: dict) -> dict:
        """Returns a dict matching schemas.match.MatchResultOut (score/matched/missing/etc)."""
        raise NotImplementedError
