"""
Phase 5 — IoT Specification & Requirement Extraction.

Turns an IoT device specification into structured, source-traceable
requirements ready for later RAG retrieval and LLM test generation.

Public API used by later phases and tests:

    ingest_text(text, ...)              - manual / TXT-style text input
    ingest_specification(path)          - TXT / JSON / PDF file input
    ingest_files(paths)                 - batch file ingestion
    IngestedSpecification / Requirement / Constraint
                                        - structured, traceable output
    RequirementCategory / RequirementSeverity
                                        - supported categories & priority
    SpecField                           - recognized source field (audit)
    SpecificationIngestionError, ...    - typed failure modes

Design rules honored here:
    - Requirements are 1:1 with recognized, parseable spec facts.
    - Nothing is invented, guessed, or executed — spec content is data.
    - Ambiguous / incomplete specs are flagged, never fabricated.
    - Scanned/image PDFs are reported as unsupported (no OCR).

Not implemented here (later phases): RAG, embeddings, vector DB, LLM
generation, autonomous refinement, dashboard.
"""

from app.ingestion.errors import (
    EmptySpecificationError,
    PdfExtractionError,
    SpecificationIngestionError,
    SpecificationParseError,
    UnreadableFileError,
    UnsupportedFormatError,
)
from app.ingestion.extractor import build_requirement, extract_requirements, id_for_index
from app.ingestion.fields import FIELD_REGISTRY, FieldDef, ValueKind, field_for_key, parse_field_value
from app.ingestion.json_parser import parse_spec_json, snake_case_key
from app.ingestion.models import (
    Constraint,
    IngestedSpecification,
    Requirement,
    RequirementCategory,
    RequirementSeverity,
    SpecField,
)
from app.ingestion.normalizer import (
    canonical_unit,
    clean_token,
    normalize_key,
    normalize_requirement_description,
)
from app.ingestion.pdf_extractor import extract_text, extract_text_pages
from app.ingestion.service import (
    SUPPORTED_FORMATS,
    ingest_files,
    ingest_specification,
    ingest_text,
)
from app.ingestion.text_parser import parse_spec_text
from app.ingestion.validator import validate_requirement, validate_requirements

__all__ = [
    # errors
    "EmptySpecificationError",
    "PdfExtractionError",
    "SpecificationIngestionError",
    "SpecificationParseError",
    "UnreadableFileError",
    "UnsupportedFormatError",
    # service
    "SUPPORTED_FORMATS",
    "ingest_files",
    "ingest_specification",
    "ingest_text",
    # models
    "Constraint",
    "IngestedSpecification",
    "Requirement",
    "RequirementCategory",
    "RequirementSeverity",
    "SpecField",
    # fields
    "FIELD_REGISTRY",
    "FieldDef",
    "ValueKind",
    "field_for_key",
    "parse_field_value",
    # parsers
    "extract_text",
    "extract_text_pages",
    "parse_spec_json",
    "parse_spec_text",
    "snake_case_key",
    # extractor
    "build_requirement",
    "extract_requirements",
    "id_for_index",
    # normalization
    "canonical_unit",
    "clean_token",
    "normalize_key",
    "normalize_requirement_description",
    # validation
    "validate_requirement",
    "validate_requirements",
]