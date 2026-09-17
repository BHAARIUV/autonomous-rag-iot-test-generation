"""
Phase 11 — unit tests for RefinementService loop behaviour (app.refinement).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.faults import FaultType, make_fault
from app.refinement import RefinementDecision, RefinementGap, RefinementService, StopReason
from app.testing.models import TestStatus

from tests.unit._analysis_helpers import make_requirement, make_result, make_test_case


class FakeSuite:
    def __init__(self, test_cases):
        self.test_cases = test_cases


class FakeGenerator:
    def __init__(self, suites):
        self._suites = suites  # dict requirement_id -> list[TestCase]

    def generate_for_requirement(self, requirement, top_k=4):
        return FakeSuite(self._suites.get(requirement.requirement_id, []))


class FakeExecutor:
    def __init__(self, status: TestStatus = TestStatus.PASS, raises=False):
        self._status = status
        self.raises = raises
        self.calls = 0

    def execute_test_cases(self, test_cases):
        if self.raises:
            raise RuntimeError("broker unavailable")
        self.calls += 1
        return ([
            make_result(tc.test_case_id, tc.requirement_id, self._status)
            for tc in test_cases
        ], SimpleNamespace())

    def execute_test_case(self, tc):
        if self.raises:
            raise RuntimeError("broker unavailable")
        return make_result(tc.test_case_id, tc.requirement_id, self._status)


def _settings(**kwargs):
    base = dict(rag_top_k=4, max_refinement_iterations=3,
                target_requirement_coverage=90.0)
    base.update(kwargs)
    return SimpleNamespace(**base)


REQS = [
    make_requirement("REQ-001"), make_requirement("REQ-002"),
    make_requirement("REQ-003"), make_requirement("REQ-004"),
]


def _only_req1_covered():
    """Only REQ-001 generated + executed; REQ-002/003/004 completely uncovered."""
    gen = FakeGenerator({
        "REQ-001": [make_test_case("TC-1", "REQ-001")],
        "REQ-002": [make_test_case("TC-2", "REQ-002")],
        "REQ-003": [make_test_case("TC-3", "REQ-003")],
        "REQ-004": [make_test_case("TC-4", "REQ-004")],
    })
    return gen, [make_test_case("TC-1", "REQ-001")], [
        make_result("TC-1", "REQ-001", TestStatus.PASS)
    ]


class TestStopTargetReached:
    def test_loop_raises_coverage_until_target(self):
        gen, tcs, res = _only_req1_covered()
        svc = RefinementService(settings_=_settings(), generator=gen,
                                executor=FakeExecutor(), max_iterations=6,
                                target_requirement_coverage=50.0)
        r = svc.run(requirements=REQS, test_cases=tcs, results=res, fault_specs=[])
        assert r.stop_reason is StopReason.TARGET_REACHED
        assert r.initial_coverage.requirement_coverage == 25.0
        assert r.final_coverage.requirement_coverage >= 50.0
        assert r.improvement_requirement_coverage > 0
        assert r.total_generated > 0
        assert r.total_executed > 0
        assert len(r.iterations) >= 1
        assert r.iterations[0].decision.value == "REGENERATE"


class TestStopMaxIterations:
    def test_max_iterations_when_target_unreachable(self):
        gen, tcs, res = _only_req1_covered()
        svc = RefinementService(settings_=_settings(), generator=gen,
                                executor=FakeExecutor(), max_iterations=2,
                                target_requirement_coverage=100.0)
        r = svc.run(requirements=REQS, test_cases=tcs, results=res, fault_specs=[])
        assert r.stop_reason is StopReason.MAX_ITERATIONS
        assert r.final_coverage.requirement_coverage == 75.0
        assert len(r.iterations) == 2


class TestStopNoGaps:
    def test_no_gaps_when_everything_covered(self):
        tcs = [make_test_case(f"TC-{i}", rid) for i, rid in
               zip(range(1, 5), ["REQ-001", "REQ-002", "REQ-003", "REQ-004"])]
        res = [make_result(tc.test_case_id, tc.requirement_id, TestStatus.PASS)
               for tc in tcs]
        svc = RefinementService(settings_=_settings(), generator=FakeGenerator({}),
                                executor=FakeExecutor())
        r = svc.run(requirements=REQS, test_cases=tcs, results=res, fault_specs=[])
        # Fully covered: the loop terminates immediately with a clean stop
        # (either NO_GAPS, or TARGET_REACHED if the 100% coverage clears the
        # default target first) and never generates/executes anything extra.
        assert r.stop_reason in (StopReason.NO_GAPS, StopReason.TARGET_REACHED)
        assert len(r.iterations) == 0
        assert r.final_coverage.requirement_coverage == 100.0
        assert r.total_generated == 0


class TestStopNoImprovement:
    def test_stops_when_generation_cannot_progress(self):
        gen, tcs, res = _only_req1_covered()
        # empty suite means regeneration yields nothing new -> no progress
        svc = RefinementService(settings_=_settings(), generator=FakeGenerator({}),
                                executor=FakeExecutor(), max_iterations=6,
                                target_requirement_coverage=100.0)
        r = svc.run(requirements=REQS, test_cases=tcs, results=res, fault_specs=[])
        assert r.stop_reason is StopReason.NO_IMPROVEMENT
        assert r.total_generated == 0
        assert r.total_executed == 0


class TestExecuteExisting:
    def test_generated_but_unexecuted_test_is_executed(self):
        tc1 = make_test_case("TC-1", "REQ-001")
        exe = FakeExecutor()
        svc = RefinementService(settings_=_settings(), generator=FakeGenerator({}),
                                executor=exe, max_iterations=3,
                                target_requirement_coverage=100.0)
        r = svc.run(requirements=[make_requirement("REQ-001")],
                    test_cases=[tc1], results=[], fault_specs=[])
        assert r.stop_reason in (StopReason.TARGET_REACHED, StopReason.NO_GAPS)
        assert any(it.decision.value == "EXECUTE_EXISTING" for it in r.iterations)
        assert r.total_executed >= 1


class TestNotAddressable:
    def test_fault_gap_is_not_addressable_and_never_generates(self):
        tc1 = make_test_case("TC-1", "REQ-001")
        res = [make_result("TC-1", "REQ-001", TestStatus.PASS)]
        faults = [make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-OOR")]
        svc = RefinementService(settings_=_settings(), generator=FakeGenerator({}),
                                executor=FakeExecutor(), max_iterations=4,
                                target_requirement_coverage=100.0)
        r = svc.run(requirements=[make_requirement("REQ-001")],
                    test_cases=[tc1], results=res, fault_specs=faults)
        # fault gaps are NOT_ADDRESSABLE -> no tests generated; the loop never
        # auto-generates a fault test (would be outside the safe action set).
        assert r.stop_reason in (StopReason.TARGET_REACHED,
                                 StopReason.NO_GAPS, StopReason.NO_IMPROVEMENT)
        assert r.total_generated == 0


class TestExecutionErrorHandled:
    def test_executor_failure_is_captured_not_crashed(self):
        gen, tcs, res = _only_req1_covered()
        svc = RefinementService(settings_=_settings(), generator=gen,
                                executor=FakeExecutor(raises=True), max_iterations=3,
                                target_requirement_coverage=100.0)
        r = svc.run(requirements=REQS, test_cases=tcs, results=res, fault_specs=[])
        # execution failure is swallowed per-iteration; loop still terminates
        assert r.stop_reason in (StopReason.NO_IMPROVEMENT, StopReason.MAX_ITERATIONS)
        assert r.iterations[0].execution_outcome == "ERROR"


class TestActionMethods:
    def test_regenerate_deduplicates_identical_content(self):
        existing = make_test_case("TC-1", "REQ-001")
        gen = FakeGenerator({"REQ-001": [make_test_case("TC-1B", "REQ-001")]})
        svc = RefinementService(settings_=_settings(), generator=gen,
                                executor=FakeExecutor())
        gap = RefinementGap(gap_id="G", gap_type="BOUNDARY_MISSING",
                            requirement_id="REQ-001", description="d",
                            severity="HIGH", recommended_action="a",
                            decision=RefinementDecision.REGENERATE)
        req_by_id = {"REQ-001": make_requirement("REQ-001")}
        working = {"TC-1": existing}
        content_seen = {(existing.requirement_id, existing.category.value,
                         tuple((s.step_number, s.action) for s in existing.test_steps),
                         existing.expected_result): "TC-1"}
        iter_, new_tcs, new_results, gen_cnt, exec_cnt = svc._act_regenerate(
            gap, 1, req_by_id, working, {}, content_seen, [])
        assert new_tcs == []  # identical content -> dropped
        assert gen_cnt == 0
        assert iter_.generated_test_case_ids == []

    def test_execute_existing_runs_the_referenced_test(self):
        tc1 = make_test_case("TC-1", "REQ-001")
        svc = RefinementService(settings_=_settings(), executor=FakeExecutor())
        gap = RefinementGap(gap_id="G", gap_type="TEST_GENERATED_NOT_EXECUTED",
                            requirement_id="REQ-001",
                            related_test_case_id="TC-1", description="d",
                            severity="HIGH", recommended_action="run TC-1",
                            decision=RefinementDecision.EXECUTE_EXISTING)
        req_by_id = {"REQ-001": make_requirement("REQ-001")}
        working = {"TC-1": tc1}
        iter_, new_tcs, new_results, gen_cnt, exec_cnt = svc._act_execute_existing(
            gap, 1, req_by_id, working, {}, [])
        assert exec_cnt == 1
        assert gen_cnt == 0
        assert new_results[0].test_case_id == "TC-1"
        assert iter_.decision is RefinementDecision.EXECUTE_EXISTING
