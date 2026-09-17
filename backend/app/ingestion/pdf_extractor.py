"""
WHAT:
    Text extraction from PDF specifications using pypdf (pure Python).

WHY:
    Phase 5 must ingest PDFs, but only *text-based* PDFs are supported.
    A scanned / image-only PDF contains no extractable text layer; there
    is no OCR in this phase. Instead of silently returning an empty or
    garbage document (which would amount to "pretending OCR happened"),
    the extractor raises `PdfExtractionError` and reports the limitation
    honestly.

HOW:
    - `extract_text_pages()` returns the per-page extracted text so the
      service can keep page-level traceability (each page is parsed with
      a `page N` reference prefix).
    - `extract_text()` joins pages with blank lines and strips the result.
    - A PDF with zero pages or with no text on any page raises
      `PdfExtractionError` with an explicit "scan/image PDF / no OCR"
      message.

HOW TO VERIFY:
    See tests/unit/test_pdf_extractor.py (text PDF vs. empty-text PDF).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.ingestion.errors import PdfExtractionError


def extract_text_pages(path: str | Path) -> list[str]:
    """Return the extracted text of each PDF page (list, one item per page)."""
    pdf_path = Path(path)
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - defensive
        raise PdfExtractionError(
            "pypdf is not installed; install it with "
            "'pip install pypdf' to enable PDF ingestion."
        ) from exc

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        logger.error(f"Failed to open PDF '{pdf_path}': {exc}")
        raise PdfExtractionError(
            f"Could not read PDF '{pdf_path}': {exc}"
        ) from exc

    if not reader.pages:
        raise PdfExtractionError(
            f"PDF '{pdf_path}' contains no pages."
        )

    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(f"Page {index} of '{pdf_path}' could not be "
                           f"extracted: {exc}")
            text = ""
        pages.append(text)

    if not any(pages):
        raise PdfExtractionError(
            f"PDF '{pdf_path}' contains no extractable text. It is likely "
            "a scanned / image-based document. OCR is NOT supported in "
            "this phase — please provide a text-based PDF or use the "
            "TXT/JSON/manual input instead."
        )

    logger.debug(
        f"Extracted text from {len(pages)} page(s) of '{pdf_path}' "
        f"(total {sum(len(p) for p in pages)} chars)."
    )
    return pages


def extract_text(path: str | Path) -> str:
    """Extract all PDF text flattened into a single string."""
    pages = extract_text_pages(path)
    return "\n\n".join(pages).strip()