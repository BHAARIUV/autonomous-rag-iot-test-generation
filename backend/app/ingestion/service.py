"""
WHAT:
    The public orchestration layer of Phase 5: one entry point that
    turns an IoT specification (TXT / JSON / PDF / manual text) into a
    validated, traceable `IngestedSpecification` full of `Requirement`s.

WHY:
    Callers (later phases, the CLI, the dashboard) should never have to
    know which parser runs for which input. The service dispatches by
    format, wires parse -> extract -> validate, and converts failures
    into typed exceptions with human-readable messages.

HOW:
    - `ingest_text(text, ...)` handles manual / TXT / PDF-extracted text.
    - `ingest_specification(path)` dispatches by file extension
      (txt/json/pdf); .txt goes through the text path, .json through the
      JSON parser, .pdf through pypdf extraction then the text path with
      page-level traceability.
    - Non-fatal findings (unrecognized fields, ambiguous values, missing
      expected fields) are collected as warnings; hard failures raise
      `SpecificationIngestionError` subclasses. Incomplete/empty
      specifications are reported honestly — never fabricated.

HOW TO VERIFY:
    See tests/unit/test_spec_service.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from loguru import logger

from app.ingestion.errors import (
    EmptySpecificationError,
    SpecificationParseError,
    UnreadableFileError,
    UnsupportedFormatError,
)
from app.ingestion.extractor import extract_requirements
from app.ingestion.fields import EXPECTED_SPEC_FIELDS
from app.ingestion.json_parser import parse_spec_json
from app.ingestion.models import IngestedSpecification, SpecField
from app.ingestion.pdf_extractor import extract_text_pages
from app.ingestion.text_parser import parse_spec_text
from app.ingestion.validator import validate_requirements

SUPPORTED_FILE_FORMATS = ("txt", "json", "pdf")
SUPPORTED_FORMATS = SUPPORTED_FILE_FORMATS + ("text", "manual")

_EXPECTED_LABELS = {
    "temperature_range": "Temperature Range",
    "temperature_accuracy": "Temperature Accuracy",
    "sampling_interval": "Sampling Interval",
    "communication_protocol": "Communication Protocol",
}


def ingest_text(
    text: str,
    source: str = "manual",
    source_format: str = "text",
) -> IngestedSpecification:
    """Ingest a specification from raw text (manual input / TXT content)."""
    if not text or not text.strip():
        raise EmptySpecificationError(
            f"Specification '{source}' is empty — nothing to extract."
        )

    fields, warnings = parse_spec_text(
        text.strip(), source, source_format, ref_prefix=None
    )
    return _finalize(source, source_format, text, fields, warnings)


# --------------------------------------------------------------------- files

def ingest_specification(path: str | Path) -> IngestedSpecification:
    """Ingest a specification file; format is derived from the extension."""
    spec_path = Path(path)
    fmt = _format_of(spec_path)

    if fmt == "pdf":
        return _ingest_pdf(spec_path)
    if fmt == "json":
        return _ingest_json(spec_path)
    return _ingest_txt(spec_path)


def ingest_files(paths: Sequence[str | Path]) -> list[IngestedSpecification]:
    """Ingest several specification files, returning one result each."""
    return [ingest_specification(p) for p in paths]


# ------------------------------------------------------------------- dispatch

def _format_of(spec_path: Path) -> str:
    ext = spec_path.suffix.lower().lstrip(".")
    if ext not in SUPPORTED_FILE_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported specification format '{ext or '(none)'}' for "
            f"'{spec_path}'. Supported formats: "
            f"{', '.join(SUPPORTED_FILE_FORMATS)}."
        )
    return ext


def _ingest_txt(spec_path: Path) -> IngestedSpecification:
    raw = _read_text(spec_path)
    if not raw.strip():
        raise EmptySpecificationError(
            f"Specification '{spec_path}' is empty — nothing to extract."
        )
    fields, warnings = parse_spec_text(raw, str(spec_path), "txt")
    return _finalize(str(spec_path), "txt", raw, fields, warnings)


def _ingest_json(spec_path: Path) -> IngestedSpecification:
    raw = _read_text(spec_path)
    if not raw.strip():
        raise EmptySpecificationError(
            f"Specification '{spec_path}' is empty — nothing to extract."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(f"Malformed JSON in '{spec_path}': {exc}")
        raise SpecificationParseError(
            f"Malformed JSON in '{spec_path}': {exc.msg} at line "
            f"{exc.lineno}."
        ) from exc

    fields, warnings = parse_spec_json(data, str(spec_path), "json")
    return _finalize(str(spec_path), "json", raw, fields, warnings)


def _ingest_pdf(spec_path: Path) -> IngestedSpecification:
    pages = extract_text_pages(spec_path)

    fields: list[SpecField] = []
    warnings: list[str] = []
    raw_parts: list[str] = []
    for page_no, page_text in enumerate(pages, start=1):
        if not page_text.strip():
            continue
        raw_parts.append(page_text)
        page_fields, page_warnings = parse_spec_text(
            page_text,
            str(spec_path),
            "pdf",
            ref_prefix=f"page {page_no}",
        )
        fields.extend(page_fields)
        warnings.extend(page_warnings)

    raw = "\n\n".join(raw_parts)
    if not fields and not raw.strip():
        raise EmptySpecificationError(
            f"PDF '{spec_path}' contained no usable specification text."
        )
    return _finalize(str(spec_path), "pdf", raw, fields, warnings)


def _read_text(spec_path: Path) -> str:
    try:
        return spec_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        logger.error(f"Specification file not found: '{spec_path}'")
        raise UnreadableFileError(
            f"Specification file not found: '{spec_path}'"
        ) from exc
    except OSError as exc:
        logger.error(f"Could not read specification file '{spec_path}': {exc}")
        raise UnreadableFileError(
            f"Could not read specification file '{spec_path}': {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise SpecificationParseError(
            f"Specification '{spec_path}' is not valid UTF-8 text: {exc}"
        ) from exc


# ------------------------------------------------------------------ finalize

def _finalize(
    source: str,
    source_format: str,
    raw_text: str,
    fields: list[SpecField],
    warnings: list[str],
) -> IngestedSpecification:
    requirements, extraction_warnings = extract_requirements(
        fields, source, source_format
    )
    warnings.extend(extraction_warnings)

    errors: list[str] = []
    if not fields:
        errors.append(
            "No recognized specification fields were found — no "
            "requirements generated."
        )
    validation_issues = validate_requirements(requirements)
    if validation_issues:
        errors.extend(validation_issues)

    missing = _missing_expected(fields)
    if fields and missing:
        warnings.append(
            "Specification appears incomplete — no entry found for: "
            + ", ".join(missing)
            + "."
        )

    result = IngestedSpecification(
        source=source,
        source_format=source_format,
        raw_text=raw_text,
        fields=fields,
        requirements=requirements,
        warnings=warnings,
        errors=errors,
    )

    logger.info(
        f"Ingested '{source}' ({source_format}): {len(requirements)} "
        f"requirement(s), {len(warnings)} warning(s), {len(errors)} error(s)."
    )
    return result


def _missing_expected(fields: list[SpecField]) -> list[str]:
    present = {f.key for f in fields}
    return [
        _EXPECTED_LABELS[expected]
        for expected in EXPECTED_SPEC_FIELDS
        if expected not in present
    ]