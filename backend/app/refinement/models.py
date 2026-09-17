"""
Phase 11 — Autonomous Refinement Loop models.

WHY:
    After an initial test suite has been generated (Phase 7), executed
    (Phase 8) and analysed (Phase 9), the loop must represent, in one typed
    object, a single pass of "identify gap -> generate -> validate -> execute
    -> re-analyse": the selected gap, the RAG evidence used, the generated /
    executed tests, the measured coverage BEFORE and AFTER, the real
    improvement, and an explicit stop reason. `RefinementResult` then holds the
    whole run so nothing is lost and no statistic is fabricated.

HOW (honesty):
    - `refinement_gap`, `retrieved_evidence`, `generated_test_cases` and the
      executed results all reference REAL ids produced by the existing phases.
    - BEFORE/AFTER coverage snapshots are derived from the Phase 9
      `CoverageSummary` before and after each iteration — never guessed.
    - `improvement` is the measured delta between the two, not a claimed value.
    - The loop stops for an explicit, recorded reason; it never silently
      continues.

HOW TO VERIFY:
    See tests/unit/test_refinement_*.py and
    tests/integration/test_refinement_full_chain.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class StopReason(str, Enum):
    """Why the refinement loop finished."""

    TARGET_REACHED = "TARGET_REACHED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    NO_IMPROVEMENT = "NO_IMPROVEMENT"
    NO_GAPS = "NO_GAPS"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class RefinementDecision(str, Enum):
    """What action a single iteration decided to take for the selected gap."""

    REGENERATE = "REGENERATE"              # create + validate + execute new tests for a requirement
    EXECUTE_EXISTING = "EXECUTE_EXISTING"  # run an already-generated but unexecuted test
    SKIP_ENVIRONMENT = "SKIP_ENVIRONMENT"  # not addressable without a runtime (e.g. MQTT broker)
    NOT_ADDRESSABLE = "NOT_ADDRESSABLE"    # no in-scope action (e.g. auto-generating a fault test)
    STOP = "STOP"


class RefinementGapType(str, Enum):
    """Refinement-facing view of an analysis gap.

    Mirrors the Phase 9 `GapType` tokens so refinement can plan against them
    without inventing new ones."""

    REQUIREMENT_NO_EXECUTED_TEST = "REQUIREMENT_NO_EXECUTED_TEST"
    REQUIREMENT_ONLY_POSITIVE = "REQUIREMENT_ONLY_POSITIVE"
    BOUNDARY_MISSING = "BOUNDARY_MISSING"
    NEGATIVE_MISSING = "NEGATIVE_MISSING"
    TEST_GENERATED_NOT_EXECUTED = "TEST_GENERATED_NOT_EXECUTED"
    TEST_SKIPPED = "TEST_SKIPPED"
    INTERFACE_NO_EXECUTED_TEST = "INTERFACE_NO_EXECUTED_TEST"
    FAULT_NO_TEST = "FAULT_NO_TEST"
    FAULT_NOT_DETECTED = "FAULT_NOT_DETECTED"


class RefinementGap(BaseModel):
    """One gap selected from real Phase 9 analysis, with an action plan."""

    model_config = {"frozen": True}

    gap_id: str
    gap_type: str
    requirement_id: str | None = None
    related_test_case_id: str | None = None
    description: str
    severity: str
    recommended_action: str
    decision: RefinementDecision = RefinementDecision.NOT_ADDRESSABLE


class CoverageSnapshot(BaseModel):
    """A measured coverage/fault state (BEFORE or AFTER an iteration)."""

    model_config = {"frozen": True}

    total_requirements: int = Field(ge=0)
    covered_requirements: int = Field(ge=0)
    requirement_coverage: float = Field(ge=0.0)
    total_test_cases: int = Field(ge=0)
    executed_test_cases: int = Field(ge=0)
    execution_coverage: float = Field(ge=0.0)
    total_faults: int = Field(ge=0)
    detected_faults: int = Field(ge=0)
    fault_detection_rate: float = Field(ge=0.0)
    gap_count: int = Field(ge=0)

    @staticmethod
    def from_summary(s: "object") -> "CoverageSnapshot":
        return CoverageSnapshot(
            total_requirements=s.total_requirements,
            covered_requirements=s.covered_requirements,
            requirement_coverage=s.requirement_coverage,
            total_test_cases=s.total_test_cases,
            executed_test_cases=s.executed_test_cases,
            execution_coverage=s.execution_coverage,
            total_faults=s.total_faults,
            detected_faults=s.detected_faults,
            fault_detection_rate=s.fault_detection_rate,
            gap_count=s.gap_count,
        )


class RefinementIteration(BaseModel):
    """One complete refinement pass, fully traceable to real artifacts."""

    model_config = {"frozen": True}

    iteration_number: int = Field(ge=1)
    selected_gap: RefinementGap | None = None
    decision: RefinementDecision
    retrieved_evidence: list[str] = Field(default_factory=list)  # RAG chunk ids used
    generated_test_case_ids: list[str] = Field(default_factory=list)
    validation_outcome: str = Field(default="NONE")  # VALIDATED / NONE / FAILED
    executed_ids: list[str] = Field(default_factory=list)  # test_case_ids executed this pass
    execution_outcome: str = Field(default="NONE")  # NONE / EXECUTED / ERROR
    coverage_before: CoverageSnapshot
    coverage_after: CoverageSnapshot
    improvement: float = Field(default=0.0, description="requirement-coverage delta, never guessed")
    attempted_gap_ids: set[str] = Field(default_factory=set)
    note: str = ""


class RefinementResult(BaseModel):
    """The full run: initial state, all iterations, final state + stop reason."""

    refinement_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    started_timestamp: datetime = Field(default_factory=_now_utc)
    finished_timestamp: datetime = Field(default_factory=_now_utc)

    initial_coverage: CoverageSnapshot
    final_coverage: CoverageSnapshot
    final_gap_count: int = Field(ge=0)
    improvement_requirement_coverage: float = Field(ge=0.0)
    improvement_execution_coverage: float = Field(ge=0.0)
    improvement_fault_detection: float = Field(ge=0.0)

    iterations: list[RefinementIteration] = Field(default_factory=list)
    stop_reason: StopReason
    stop_detail: str = ""

    total_generated: int = Field(default=0, ge=0, description="new test cases generated across the run")
    total_executed: int = Field(default=0, ge=0, description="new executions performed across the run")
    final_test_case_ids: list[str] = Field(default_factory=list)
    final_result_ids: list[str] = Field(default_factory=list)


__all__ = [
    "StopReason",
    "RefinementDecision",
    "RefinementGapType",
    "RefinementGap",
    "CoverageSnapshot",
    "RefinementIteration",
    "RefinementResult",
]
