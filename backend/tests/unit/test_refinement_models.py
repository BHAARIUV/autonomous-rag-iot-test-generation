"""
Phase 11 — unit tests for the refinement models (app.refinement.models).
"""

from __future__ import annotations

import pytest

from app.refinement.models import (
    CoverageSnapshot,
    RefinementDecision,
    RefinementGap,
    RefinementGapType,
    RefinementIteration,
    RefinementResult,
    StopReason,
)


def _snap(**kw) -> CoverageSnapshot:
    defaults = dict(
        total_requirements=4, covered_requirements=2, requirement_coverage=50.0,
        total_test_cases=6, executed_test_cases=6, execution_coverage=100.0,
        total_faults=2, detected_faults=0, fault_detection_rate=0.0, gap_count=2,
    )
    defaults.update(kw)
    return CoverageSnapshot(**defaults)


class TestEnums:
    def test_stop_reasons(self):
        assert StopReason.TARGET_REACHED.value == "TARGET_REACHED"
        assert StopReason.TARGET_REACHED in StopReason
        assert {r.value for r in StopReason} == {
            "TARGET_REACHED", "MAX_ITERATIONS", "NO_IMPROVEMENT",
            "NO_GAPS", "VALIDATION_FAILURE", "EXECUTION_ERROR",
        }

    def test_decisions(self):
        assert RefinementDecision.REGENERATE.value == "REGENERATE"
        assert {d.value for d in RefinementDecision} == {
            "REGENERATE", "EXECUTE_EXISTING", "SKIP_ENVIRONMENT",
            "NOT_ADDRESSABLE", "STOP",
        }

    def test_gap_types(self):
        assert RefinementGapType.REQUIREMENT_NO_EXECUTED_TEST.value == "REQUIREMENT_NO_EXECUTED_TEST"
        assert RefinementGapType.BOUNDARY_MISSING in RefinementGapType


class TestRefinementGap:
    def test_frozen(self):
        gap = RefinementGap(
            gap_id="G1", gap_type="BOUNDARY_MISSING", requirement_id="REQ-001",
            description="d", severity="HIGH", recommended_action="a",
            decision=RefinementDecision.REGENERATE,
        )
        with pytest.raises(Exception):
            gap.description = "changed"

    def test_default_decision(self):
        gap = RefinementGap(gap_id="G1", gap_type="NEGATIVE_MISSING",
                            description="d", severity="LOW", recommended_action="a")
        assert gap.decision is RefinementDecision.NOT_ADDRESSABLE

    def test_optional_fields(self):
        gap = RefinementGap(gap_id="G1", gap_type="X", description="d",
                            severity="LOW", recommended_action="a")
        assert gap.requirement_id is None
        assert gap.related_test_case_id is None


class TestCoverageSnapshot:
    def test_from_summary_round_trip(self):
        class FakeSummary:
            total_requirements = 4
            covered_requirements = 3
            requirement_coverage = 75.0
            total_test_cases = 10
            executed_test_cases = 7
            execution_coverage = 70.0
            total_faults = 2
            detected_faults = 1
            fault_detection_rate = 50.0
            gap_count = 1

        snap = CoverageSnapshot.from_summary(FakeSummary())
        assert snap.requirement_coverage == 75.0
        assert snap.covered_requirements == 3
        assert snap.gap_count == 1
        assert snap.fault_detection_rate == 50.0

    def test_non_negative_constraints(self):
        with pytest.raises(Exception):
            CoverageSnapshot(total_requirements=4, covered_requirements=2,
                             requirement_coverage=-1.0, total_test_cases=6,
                             executed_test_cases=6, execution_coverage=100.0,
                             total_faults=2, detected_faults=0,
                             fault_detection_rate=0.0, gap_count=2)


class TestRefinementIteration:
    def test_defaults(self):
        b = _snap()
        it = RefinementIteration(
            iteration_number=1, decision=RefinementDecision.REGENERATE,
            coverage_before=b, coverage_after=b,
        )
        assert it.generated_test_case_ids == []
        assert it.retrieved_evidence == []
        assert it.validation_outcome == "NONE"
        assert it.execution_outcome == "NONE"
        assert it.improvement == 0.0
        assert it.attempted_gap_ids == set()

    def test_frozen(self):
        b = _snap()
        it = RefinementIteration(iteration_number=1,
                                 decision=RefinementDecision.STOP,
                                 coverage_before=b, coverage_after=b)
        with pytest.raises(Exception):
            it.note = "x"


class TestRefinementResult:
    def test_defaults(self):
        b = _snap()
        r = RefinementResult(
            initial_coverage=b, final_coverage=b, final_gap_count=2,
            improvement_requirement_coverage=0.0,
            improvement_execution_coverage=0.0,
            improvement_fault_detection=0.0,
            stop_reason=StopReason.NO_GAPS,
        )
        assert r.refinement_id
        assert r.iterations == []
        assert r.total_generated == 0
        assert r.stop_detail == ""

    def test_has_unique_refinement_id(self):
        b = _snap()
        make = lambda: RefinementResult(
            initial_coverage=b, final_coverage=b, final_gap_count=0,
            improvement_requirement_coverage=0.0,
            improvement_execution_coverage=0.0,
            improvement_fault_detection=0.0,
            stop_reason=StopReason.NO_GAPS,
        )
        assert make().refinement_id != make().refinement_id
