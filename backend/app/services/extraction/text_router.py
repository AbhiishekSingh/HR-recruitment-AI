from pathlib import Path

from app.services.extraction.pdf_extractor import extract_pdf_text, extract_pdf_text_with_ocr
from app.services.extraction.docx_extractor import extract_docx_text


def extract_text(file_path: str) -> str:
    """Routes to the right extractor by file extension, with OCR fallback for scanned PDFs."""
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        text, needs_ocr = extract_pdf_text(file_path)
        if needs_ocr:
            text = extract_pdf_text_with_ocr(file_path)
        return text

    if ext == ".docx":
        return extract_docx_text(file_path)

    raise ValueError(f"Unsupported file type: {ext}")
