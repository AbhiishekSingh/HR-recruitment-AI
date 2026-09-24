import pdfplumber

MIN_TEXT_LENGTH = 50  # below this, assume scanned/image PDF and flag for vision extraction


def extract_pdf_text(file_path: str) -> tuple[str, bool]:
    """Returns (text, needs_vision_fallback). `needs_vision_fallback` is
    True for a scanned/image-only PDF with no usable text layer -- the
    caller (text_router.extract_text) turns that into a ScannedPDFError so
    an async caller can fall back to GPT-5 vision extraction instead of a
    separate OCR engine."""
    parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    return text, len(text) < MIN_TEXT_LENGTH
