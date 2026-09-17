"""
Phase 5 unit tests: PDF text extraction — a text-based PDF extracts cleanly
and is ingested page-aware; a scanned/empty PDF is reported honestly.
"""

import pytest

from app.ingestion.errors import PdfExtractionError
from app.ingestion.pdf_extractor import extract_text, extract_text_pages
from app.ingestion.service import ingest_specification

from tests.unit._pdf_helpers import build_blank_pdf, build_pdf

SPEC_TEXT = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Sampling Interval: 1 second\n"
    "Communication Protocol: MQTT\n"
)


def test_extract_text_from_text_based_pdf(tmp_path):
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(build_pdf([SPEC_TEXT]))

    text = extract_text(pdf_path)
    assert "Temperature Sensor" in text
    assert "Sampling Interval: 1 second" in text


def test_extract_text_pages_returns_per_page(tmp_path):
    pdf_path = tmp_path / "multi.pdf"
    pdf_path.write_bytes(
        build_pdf(["Device: Temperature Sensor", "Range: -40 C to 125 C"])
    )

    pages = extract_text_pages(pdf_path)
    assert len(pages) == 2
    assert "Device: Temperature Sensor" in pages[0]
    assert "Range: -40 C to 125 C" in pages[1]


def test_pdf_without_text_raises_honest_error(tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(build_blank_pdf())

    with pytest.raises(PdfExtractionError) as excinfo:
        extract_text_pages(pdf_path)
    message = str(excinfo.value)
    assert "no extractable text" in message.lower()
    assert "ocr" in message.lower()


def test_missing_pdf_raises(tmp_path):
    with pytest.raises(PdfExtractionError):
        extract_text_pages(tmp_path / "does-not-exist.pdf")


def test_pdf_requirements_are_page_traceable(tmp_path):
    pdf_path = tmp_path / "spec.pdf"
    pdf_path.write_bytes(
        build_pdf(
            [
                "Device: Temperature Sensor",
                "Range: -40 C to 125 C",
                "Sampling Interval: 1 second",
            ]
        )
    )

    result = ingest_specification(pdf_path)
    assert result.source_format == "pdf"
    assert len(result.requirements) == 2
    assert result.requirements[0].source_reference == "page 2 · line 1"
    assert result.requirements[1].source_reference == "page 3 · line 1"
    assert result.requirements[0].source == str(pdf_path)