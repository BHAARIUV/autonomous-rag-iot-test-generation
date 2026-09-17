"""
Phase 9 — Coverage & Fault Analysis models.

WHY:
    After tests have been generated (Phase 7) and executed (Phase 8), a
    reviewer must be able to see, in one typed object, HOW well the executed
    suite covers the requirements, which test categories / interfaces were
    exercised, which injected faults were actually DETECTED (not merely
    injected), and where the meaningful holes are. One strict, frozen,
    JSON-serializable schema forces every downstream consumer (reporting,
    dashboard, refinement) to speak the same language and keeps
    "execution coverage" clearly distinct from "pass rate".

HOW (coverage rules — deterministic):
    - EXECUTED means a real Phase 8 `ExecutionResult` exists with status
      PASS or FAIL. Both genuinely drove actions + assertions against the
      device, so both count toward execution coverage and requirement
      coverage. `ExecutionResult.status` values map one-to-one:
          PASS    -> executed, counted
          FAIL    -> executed, counted
          ERROR   -> executed attempt that could not complete -> NOT counted
                     as coverage (reported separately in `errors`)
          SKIPPED -> execution never attempted -> NOT counted (reported in
                     `skipped`)
    - A requirement is COVERED iff at least one of its tests has an
      executed (PASS/FAIL) result. Generated-only, SKIPPED and ERROR tests
      never cover a requirement on their own.
    - PASS rate = passed / total * 100 (consistent with Phase 8's
      `ExecutionSummary.pass_rate`, so the two engines agree).
    - Execution coverage = executed / total * 100 (executed = PASS + FAIL).
    - Fault DETECTION requires evidence: a fault a test injected is DETECTED
      only if that test ended in FAIL (an assertion actually evaluated the
      faulted behavior and surfaced it). Injecting a fault with no failing
      assertion counts as injected-but-missed, never assumed detected.

HOW TO VERIFY:
    See tests/unit/test_analysis_*.py and
    tests/integration/test_analysis_full_chain.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Test-category coverage: the union of categories already understood by the
# Phase 7 `TestCategory` enum (POSITIVE/BOUNDARY/NEGATIVE/EQUIVALENCE/...).
# Additional categories flow through generically.

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

GapType = Literal[
    "REQUIREMENT_NO_EXECUTED_TEST",
    "REQUIREMENT_ONLY_POSITIVE",
    "BOUNDARY_MISSING",
    "NEGATIVE_MISSING",
    "FAULT_NO_TEST",
    "FAULT_NOT_DETECTED",
    "INTERFACE_NO_EXECUTED_TEST",
    "TEST_GENERATED_NOT_EXECUTED",
    "TEST_SKIPPED",
]


# ---------------------------------------------------------------------------
# Requirement coverage
# ---------------------------------------------------------------------------


class RequirementCoverage(BaseModel):
    """Per-requirement coverage from ACTUAL execution results only."""

    model_config = {"frozen": True}

    requirement_id: str = Field(description="Source requirement id (traceability)")
    category: str = Field(description="Requirement category, e.g. RANGE/COMMUNICATION")
    total_generated: int = Field(ge=0, description="Tests generated for this requirement")
    executed: int = Field(ge=0, description="PASS+FAIL results (genuinely executed)")
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0, description="Executed attempt that could not complete")
    skipped: int = Field(ge=0, description="Execution never attempted")
    covered: bool = Field(
        description="True iff at least one associated test actually executed (PASS/FAIL)"
    )


# ---------------------------------------------------------------------------
# Test-category coverage
# ---------------------------------------------------------------------------


class CategoryTestCoverage(BaseModel):
    """Executed-test statistics for one test category (e.g. POSITIVE)."""

    model_config = {"frozen": True}

    category: str = Field(description="Test category, e.g. POSITIVE/BOUNDARY/NEGATIVE")
    total: int = Field(ge=0, description="Total generated tests in this category")
    executed: int = Field(ge=0, description="PASS+FAIL results")
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    execution_coverage: float = Field(
        ge=0.0, description="executed/total*100, 0 when total is 0"
    )
    pass_rate: float = Field(ge=0.0, description="passed/total*100, 0 when total is 0")


class TestCoverage(BaseModel):
    """Overall executed-test statistics, including the per-category split."""

    model_config = {"frozen": True}

    total: int = Field(ge=0)
    executed: int = Field(ge=0, description="PASS+FAIL results")
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    execution_coverage: float = Field(ge=0.0, description="executed/total*100, 0 if empty")
    pass_rate: float = Field(ge=0.0, description="passed/total*100, 0 if empty")
    by_category: list[CategoryTestCoverage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Interface / protocol coverage
# ---------------------------------------------------------------------------


class InterfaceCoverage(BaseModel):
    """Executed-test statistics for one supported IoT interface/protocol."""

    model_config = {"frozen": True}

    interface: str = Field(description="Interface label, e.g. 'Sensor/simulator' or 'MQTT'")
    protocol: str = Field(description="Underlying protocol value, e.g. SENSOR/MQTT")
    total: int = Field(ge=0, description="Tests targeting this interface")
    executed: int = Field(ge=0, description="PASS+FAIL results")
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    covered: bool = Field(
        description="True iff at least one test targeting this interface executed (PASS/FAIL)"
    )


# ---------------------------------------------------------------------------
# Fault detection coverage
# ---------------------------------------------------------------------------


class FaultCoverage(BaseModel):
    """Per-fault-type detection statistics, from real execution evidence."""

    model_config = {"frozen": True}

    fault_id: str = Field(description="Representative FaultSpec fault_id (traceability)")
    fault_type: str = Field(description="Canonical FaultType, e.g. SENSOR_OUT_OF_RANGE")
    detected: bool = Field(description="True iff at least one injected occurrence was detected")
    injected_count: int = Field(ge=0, description="Results that injected this fault type")
    detected_count: int = Field(
        ge=0, description="Injected results that ended FAIL (assertion surfaced the fault)"
    )
    missed_count: int = Field(ge=0, description="injected - detected")
    detection_rate: float = Field(ge=0.0, description="detected/injected*100, 0 if injected==0")
    related_test_cases: list[str] = Field(
        default_factory=list, description="test_case_ids that injected this fault type"
    )


# ---------------------------------------------------------------------------
# Coverage gaps
# ---------------------------------------------------------------------------


class CoverageGap(BaseModel):
    """One structured, actionable testing gap. Phase 9 only IDENTIFIES gaps."""

    model_config = {"frozen": True}

    gap_id: str = Field(description="Stable id within a report, e.g. GAP-001")
    type: GapType
    requirement_id: str | None = Field(default=None)
    related_test_case_id: str | None = Field(default=None)
    description: str = Field(description="What is missing, factually")
    severity: Severity = Field(description="LOW/MEDIUM/HIGH/CRITICAL")
    recommended_action: str = Field(description="What a later phase could do (not executed here)")


# ---------------------------------------------------------------------------
# Summary + report
# ---------------------------------------------------------------------------


class CoverageSummary(BaseModel):
    """Aggregate, deterministic coverage numbers for a batch of results."""

    model_config = {"frozen": True}

    total_requirements: int = Field(ge=0)
    covered_requirements: int = Field(ge=0)
    requirement_coverage: float = Field(
        ge=0.0, description="covered/total*100, 0 when total is 0"
    )
    total_test_cases: int = Field(ge=0, description="All generated test cases supplied")
    executed_test_cases: int = Field(ge=0, description="PASS+FAIL results")
    execution_coverage: float = Field(ge=0.0, description="executed/total*100, 0 if empty")
    pass_rate: float = Field(ge=0.0, description="passed/total*100, 0 if empty")
    total_faults: int = Field(ge=0, description="Distinct known fault types considered")
    detected_faults: int = Field(ge=0, description="Fault types with at least one detection")
    fault_detection_rate: float = Field(
        ge=0.0, description="detected/injected*100; 0 when no faults were injected"
    )
    gap_count: int = Field(ge=0, description="Number of identified gaps")


class AnalysisReport(BaseModel):
    """The full serializable outcome of one Phase 9 analysis run."""

    model_config = {"frozen": True}

    analysis_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = Field(default_factory=_now_utc)
    summary: CoverageSummary
    requirement_coverage: list[RequirementCoverage] = Field(default_factory=list)
    test_coverage: TestCoverage
    interface_coverage: list[InterfaceCoverage] = Field(default_factory=list)
    fault_coverage: list[FaultCoverage] = Field(default_factory=list)
    gaps: list[CoverageGap] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
