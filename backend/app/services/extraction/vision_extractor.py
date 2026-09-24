import base64

import fitz  # PyMuPDF

# Resumes are almost never more than a couple of pages; capping this bounds
# both the GPT-5 vision call's cost and its latency on the rare oversized
# file, rather than silently sending (and paying for) 20+ page images.
MAX_VISION_PAGES = 4

# 200 DPI is enough for GPT-5 to read normal resume body text reliably
# without producing enormous images (which cost more tokens and are slower
# to upload) -- higher only helps for very small/dense fonts.
RENDER_DPI = 200


def render_pdf_pages_to_base64_png(file_path: str, max_pages: int = MAX_VISION_PAGES) -> list[str]:
    """Renders each page of a PDF to a base64-encoded PNG, for feeding to a
    vision-capable LLM as image content. Uses PyMuPDF, which bundles its own
    rendering engine in the pip wheel -- unlike pdf2image (which shells out
    to Poppler's `pdftoppm`), this needs no system binary installed, so it
    works on a bare Windows/Linux machine with nothing but `pip install`."""
    images: list[str] = []
    doc = fitz.open(file_path)
    try:
        for page in doc[:max_pages]:
            pixmap = page.get_pixmap(dpi=RENDER_DPI)
            images.append(base64.b64encode(pixmap.tobytes("png")).decode("ascii"))
    finally:
        doc.close()
    return images
