"""
WHAT:
    The structured data model of a Phase 5 requirement-ingestion run:
    requirement category, severity, constraints, the requirement itself,
    parsed specification fields, and the final ingested result.

WHY:
    Requirements produced here become the seed for later phases (RAG
    retrieval, LLM test generation, coverage analysis). They must be a
    single, typed, JSON-serializable contract so every downstream module
    agrees on what a "requirement" is. Every requirement is traceable to
    the source specification via `source` + `source_reference`.

HOW:
    - `RequirementCategory` enumerates the supported requirement kinds.
    - `RequirementSeverity` grades priority (values aligned with the
      Phase 4 fault severities for consistency).
    - `Constraint` is one machine-readable constraint (min/max/value/
      enum/format) with an optional unit.
    - `Requirement` is one extracted, traceable requirement (immutable).
    - `SpecField` is one recognized field parsed out of a specification
      (kept for auditability and for downstream RAG source-text lookup).
    - `IngestedSpecification` is the complete result of one ingestion:
      the source, the parsed fields, the extracted requirements, and the
      warnings/errors collected along the way.

HOW TO VERIFY:
    See tests/unit/test_spec_models.py and tests/unit/test_spec_validator.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

# A fixed set of constraint kinds used when rendering requirements.
# Kept as a plain frozenset so validators can stay dependency-free.
CONSTRAINT_KINDS = frozenset({"min", "max", "value", "enum", "format", "rate"})


class RequirementCategory(str, Enum):
    """Supported requirement categories."""

    FUNCTIONAL = "FUNCTIONAL"
    RANGE = "RANGE"
    ACCURACY = "ACCURACY"
    TIMING = "TIMING"
    COMMUNICATION = "COMMUNICATION"
    DATA_VALIDATION = "DATA_VALIDATION"
    RELIABILITY = "RELIABILITY"
    SAFETY = "SAFETY"


class RequirementSeverity(str, Enum):
    """Priority grading for a requirement.

    Values deliberately match Phase 4's `FaultSeverity` so the project
    speaks one severity language end-to-end.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Constraint(BaseModel):
    """One machine-readable constraint of a requirement."""

    kind: str = Field(description="min | max | value | enum | format | rate")
    value: str = Field(description="Normalized constraint value")
    unit: str | None = Field(
        default=None, description="Canonical unit symbol, e.g. '°C', 's', 'V'"
    )

    model_config = {"frozen": True}

    @field_validator("kind")
    @classmethod
    def _kind_supported(cls, v: str) -> str:
        if v not in CONSTRAINT_KINDS:
            raise ValueError(
                f"unsupported constraint kind '{v}'; "
                f"expected one of {sorted(CONSTRAINT_KINDS)}"
            )
        return v

    @field_validator("value")
    @classmethod
    def _value_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("constraint value must not be blank")
        return v


class Requirement(BaseModel):
    """One extracted, source-traceable requirement."""

    model_config = {"frozen": True}

    requirement_id: str = Field(
        description="Sequential id assigned at extraction, e.g. 'REQ-001'"
    )
    description: str = Field(description="Normalized, human-readable requirement")
    category: RequirementCategory
    constraints: list[Constraint] = Field(default_factory=list)
    severity: RequirementSeverity = RequirementSeverity.MEDIUM

    # --- Traceability (REQUIRED for every requirement) ---
    source: str = Field(description="File name / 'manual' the requirement came from")
    source_reference: str = Field(
        description="Exact pointer into the source: line number, JSON path or page"
    )

    # Marked True by the extractor; validation of completeness (id format,
    # traceability, non-blank text) is the job of validator.py.
    normalized: bool = True


class SpecField(BaseModel):
    """One recognized field parsed out of a source specification."""

    key: str = Field(description="Canonical field key, e.g. 'temperature_range'")
    label: str = Field(description="Source label, e.g. 'Range'")
    raw_value: str = Field(description="Verbatim value text as found in the source")
    parsed_value: str | None = Field(
        default=None, description="Normalized value, e.g. '-40 to 125'"
    )
    unit: str | None = Field(
        default=None, description="Canonical unit symbol, e.g. '°C'"
    )
    components: dict[str, str] = Field(
        default_factory=dict,
        description="Named parsed parts, e.g. {'min': '-40', 'max': '125'}",
    )
    source_reference: str = Field(
        description="Line number, JSON path or page within the source"
    )
    category: RequirementCategory | None = Field(
        default=None,
        description="Requirement category; None for pure metadata (e.g. device name)",
    )
    parseable: bool = Field(
        default=True,
        description="False when the value is ambiguous and could not be parsed",
    )
    ambiguity_note: str | None = Field(
        default=None,
        description="Why the value was flagged ambiguous/incomplete, when relevant",
    )

    model_config = {"frozen": True}


class IngestedSpecification(BaseModel):
    """The complete result of one specification ingestion."""

    source: str = Field(description="File name / path or 'manual'")
    source_format: str = Field(description="txt | json | pdf | text")
    raw_text: str = Field(default="", description="Raw text that was analyzed")
    fields: list[SpecField] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def requirement_count(self) -> int:
        return len(self.requirements)