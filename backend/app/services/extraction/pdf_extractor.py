import pdfplumber

MIN_TEXT_LENGTH = 50  # below this, assume scanned/image PDF and flag for OCR


def extract_pdf_text(file_path: str) -> tuple[str, bool]:
    """Returns (text, needs_ocr_fallback)."""
    parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts).strip()
    return text, len(text) < MIN_TEXT_LENGTH


def extract_pdf_text_with_ocr(file_path: str) -> str:
    """Fallback for scanned PDFs with no text layer."""
    import pytesseract
    from pdf2image import convert_from_path

    images = convert_from_path(file_path)
    return "\n".join(pytesseract.image_to_string(img) for img in images)
