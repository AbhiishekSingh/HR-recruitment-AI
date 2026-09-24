from pathlib import Path

from app.services.extraction.pdf_extractor import extract_pdf_text
from app.services.extraction.docx_extractor import extract_docx_text


class ScannedPDFError(Exception):
    """Raised when a PDF has no usable text layer (a scanned/photographed
    resume, or one exported as flattened images). Callers that can await an
    LLM call should catch this and fall back to
    vision_extractor.render_pdf_pages_to_base64_png() +
    LLMProvider.extract_resume_from_images() -- GPT-5 vision reads the page
    images directly, so no separate OCR engine (Tesseract/Poppler) needs to
    be installed anywhere."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        super().__init__(f"No extractable text layer in {file_path} -- needs vision extraction")


def extract_text(file_path: str) -> str:
    """Routes to the right extractor by file extension. Stays synchronous
    and non-LLM by design (see tasks_ingestion.py's asyncio.run()-per-task
    structure) -- a scanned PDF raises ScannedPDFError instead of doing OCR
    inline, so the (async) caller decides how to handle it."""
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        text, needs_vision = extract_pdf_text(file_path)
        if needs_vision:
            raise ScannedPDFError(file_path)
        return text

    if ext == ".docx":
        return extract_docx_text(file_path)

    raise ValueError(f"Unsupported file type: {ext}")
