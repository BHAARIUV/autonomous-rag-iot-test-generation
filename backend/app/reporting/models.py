"""
Phase 10 — Final Reporting & Traceability models.

WHY:
    After all pipeline phases have run, a reviewer must be able to read one
    strict, serializable object that lays the ENTIRE chain end-to-end:

        Specification -> Requirement -> RAG evidence -> Test case ->
        validation -> execution -> fault -> coverage -> final report

    Every link must reference REAL ids from the existing system (requirement_id,
    test_case_id, execution_id, fault_id, fault_type, chunk/document ids).
    Nothing here is fabricated: coverage values come from Phase 9, execution
    statuses from Phase 8, fault evidence from Phase 4/8, test counts from a
    real pytest run.

HOW (honesty):
    - Validation status is "VALIDATED" only for strict, Phase 7-validated
      TestCase records.
    - Fault DETECTION is never inferred: it requires an execution result whose
      assertion (FAIL) actually surfaced the injected fault.
    - Detected/Missed/Not-executed/Not-applicable are mutually exclusive and
      derived from evidence, not assumptions.

HOW TO VERIFY:
    See tests/unit/test_reporting_*.py and
    tests/integration/test_reporting_full_chain.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.models import CoverageGap, CoverageSummary


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class PhaseStatus(str, Enum):
    """Completion status of a project phase."""

    COMPLETE = "COMPLETE"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FaultDetectionStatus(str, Enum):
    """Detection state of a fault, derived ONLY from execution evidence."""

    DETECTED = "DETECTED"
    MISSED = "MISSED"
    NOT_EXECUTED = "NOT_EXECUTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class InjectionStatus(str, Enum):
    """Whether a known fault was actually injected by any executed test."""

    INJECTED = "INJECTED"
    NOT_EXECUTED = "NOT_EXECUTED"


class ValidationStatus(str, Enum):
    """Whether a test case passed Phase 7 structured validation."""

    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


# ---------------------------------------------------------------------------
# Phase status
# ---------------------------------------------------------------------------


class PhaseEntry(BaseModel):
    """One phase of the project and its (evidence-backed) completion state."""

    model_config = {"frozen": True}

    phase_number: int = Field(ge=1)
    title: str
    status: PhaseStatus
    major_feature: str
    verification: str = Field(description="How the phase is verified, in words")


# ---------------------------------------------------------------------------
# Traceability records
# ---------------------------------------------------------------------------


class RagEvidence(BaseModel):
    """RAG/source knowledge referenced when generating a test case."""

    model_config = {"frozen": True}

    chunk_id: str
    document_id: str
    source: str
    topic: str
    relevance: float | None = Field(default=None, ge=0.0, le=1.0)


class TestCaseExecutionLink(BaseModel):
    """One execution of a test case, linked by the real execution_id."""

    model_config = {"frozen": True}

    execution_id: str
    execution_status: str  # PASS/FAIL/ERROR/SKIPPED
    fault_types_injected: list[str] = Field(default_factory=list)


class TestCaseTraceability(BaseModel):
    """Full trace of one validated test case through validation + execution."""

    model_config = {"frozen": True}

    test_case_id: str
    requirement_id: str
    category: str
    priority: str
    protocol: str | None = None
    interface: str | None = None
    validation_status: ValidationStatus = ValidationStatus.VALIDATED
    rag_evidence: list[RagEvidence] = Field(default_factory=list)
    executions: list[TestCaseExecutionLink] = Field(default_factory=list)
    has_executed: bool = Field(description="Any execution with PASS/FAIL")
    final_status: str | None = Field(default=None)


class RequirementTraceability(BaseModel):
    """One requirement and everything traceable to / from it."""

    model_config = {"frozen": True}

    requirement_id: str
    category: str
    description: str
    source: str
    source_reference: str
    spec_evidence: list[RagEvidence] = Field(
        default_factory=list,
        description="RAG source evidence carried by its generated tests",
    )
    tests: list[TestCaseTraceability] = Field(default_factory=list)
    associated_fault_types: list[str] = Field(default_factory=list)
    covered: bool
    has_failing_test: bool
    missing_execution_evidence: bool


class FaultTraceability(BaseModel):
    """One known fault and its evidence-backed detection state."""

    model_config = {"frozen": True}

    fault_id: str
    fault_type: str
    requirement_ids: list[str] = Field(default_factory=list)
    related_test_case_ids: list[str] = Field(default_factory=list)
    injection_status: InjectionStatus
    injection_evidence: list[str] = Field(
        default_factory=list, description="test_case_ids that injected this fault"
    )
    detection_status: FaultDetectionStatus
    execution_result: str | None = Field(default=None)
    detection_evidence: str = Field(description="Why this detection state holds")


# ---------------------------------------------------------------------------
# Test summary (from a real pytest run)
# ---------------------------------------------------------------------------


class FinalTestSummary(BaseModel):
    """Actual pytest run tally. Never guessed — callers pass real numbers."""

    model_config = {"frozen": True}

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)


# ---------------------------------------------------------------------------
# Final project report
# ---------------------------------------------------------------------------


class FinalProjectSummary(BaseModel):
    """Single view of the whole project's measured state."""

    model_config = {"frozen": True}

    project_id: str
    status: str = "COMPLETE"
    generated_timestamp: datetime = Field(default_factory=_now_utc)
    requirement_count: int = Field(ge=0)
    test_case_count: int = Field(ge=0)
    executed_test_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    execution_coverage: float = Field(ge=0.0)
    requirement_coverage: float = Field(ge=0.0)
    fault_count: int = Field(ge=0)
    detected_fault_count: int = Field(ge=0)
    fault_detection_rate: float = Field(ge=0.0)
    gap_count: int = Field(ge=0)
    recommendations: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)


class FinalProjectReport(BaseModel):
    """The complete, serializable final project report."""

    analysis_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    project_id: str = "autonomous-rag-iot-test-generation"
    project_name: str = "Autonomous RAG-Based IoT Test Generation & Fault Detection Framework"
    generated_timestamp: datetime = Field(default_factory=_now_utc)
    status: str = "COMPLETE"

    phases: list[PhaseEntry] = Field(default_factory=list)
    requirements: list[RequirementTraceability] = Field(default_factory=list)
    faults: list[FaultTraceability] = Field(default_factory=list)
    gaps: list[CoverageGap] = Field(default_factory=list)
    coverage: CoverageSummary
    test_summary: FinalTestSummary
    summary: FinalProjectSummary
