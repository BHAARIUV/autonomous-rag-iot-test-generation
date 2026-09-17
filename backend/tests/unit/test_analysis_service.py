"""
Phase 9 unit tests — the AnalysisService calculations.

Exercises every calculation against small, known datasets:
- requirement coverage
- test-category coverage
- interface/protocol coverage
- fault detection + fault detection rate
- gap detection
- empty-result handling
- duplicate ids
- PASS vs FAIL execution coverage, SKIPPED, ERROR handling
- requirement & fault traceability
"""

import pytest

from app.analysis import AnalysisService
from app.faults import FaultType
from app.ingestion.models import RequirementCategory
from app.llm.models import TestCategory
from app.testing.models import TestStatus

from tests.unit._analysis_helpers import (
    make_known_faults,
    make_requirement,
    make_result,
    make_test_case,
)


# ----------------------------------------------------------------------
# Requirement coverage
# ----------------------------------------------------------------------


def test_requirement_requires_actual_execution():
    req = make_requirement("REQ-001")
    # 2 generated tests, NONE executed
    tcs = [make_test_case("TC-1", "REQ-001"), make_test_case("TC-2", "REQ-001")]
    cov = AnalysisService.analyze_requirement_coverage([req], tcs, [])
    assert len(cov) == 1
    assert cov[0].covered is False
    assert cov[0].total_generated == 2
    assert cov[0].executed == 0


def test_requirement_covered_by_one_passed_test():
    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-1", "REQ-001"), make_test_case("TC-2", "REQ-001")]
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS)]
    cov = AnalysisService.analyze_requirement_coverage([req], tcs, results)
    assert cov[0].covered is True
    assert cov[0].executed == 1
    assert cov[0].passed == 1
    assert cov[0].failed == 0


def test_skipped_test_does_not_cover_requirement():
    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-1", "REQ-001")]
    results = [make_result("TC-1", "REQ-001", TestStatus.SKIPPED)]
    cov = AnalysisService.analyze_requirement_coverage([req], tcs, results)
    assert cov[0].covered is False
    assert cov[0].executed == 0
    assert cov[0].skipped == 1


def test_error_test_does_not_cover_requirement():
    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-1", "REQ-001")]
    results = [make_result("TC-1", "REQ-001", TestStatus.ERROR)]
    cov = AnalysisService.analyze_requirement_coverage([req], tcs, results)
    assert cov[0].covered is False
    assert cov[0].executed == 0
    assert cov[0].errors == 1


def test_fail_still_counts_as_execution_and_covers():
    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-1", "REQ-001")]
    results = [make_result("TC-1", "REQ-001", TestStatus.FAIL)]
    cov = AnalysisService.analyze_requirement_coverage([req], tcs, results)
    assert cov[0].covered is True
    assert cov[0].executed == 1
    assert cov[0].failed == 1


def test_two_requirements_only_second_covered():
    reqs = [make_requirement("REQ-001"), make_requirement("REQ-002")]
    tcs = [
        make_test_case("TC-1", "REQ-001"),
        make_test_case("TC-2", "REQ-002"),
    ]
    results = [make_result("TC-2", "REQ-002", TestStatus.PASS)]
    cov = {c.requirement_id: c for c in
           AnalysisService.analyze_requirement_coverage(reqs, tcs, results)}
    assert cov["REQ-001"].covered is False
    assert cov["REQ-002"].covered is True


# ----------------------------------------------------------------------
# Test-category coverage
# ----------------------------------------------------------------------

_CATS = [
    (TestCategory.POSITIVE, TestStatus.PASS),
    (TestCategory.BOUNDARY, TestStatus.PASS),
    (TestCategory.BOUNDARY, TestStatus.PASS),
    (TestCategory.NEGATIVE, TestStatus.FAIL),
    (TestCategory.EQUIVALENCE, TestStatus.SKIPPED),
]


def test_category_coverage_distribution():
    tcs = [
        make_test_case(f"TC-{i}", "REQ-001", cat)
        for i, (cat, _) in enumerate(_CATS)
    ]
    results = [
        make_result(f"TC-{i}", "REQ-001", status)
        for i, (_, status) in enumerate(_CATS)
    ]
    tc = AnalysisService.analyze_test_coverage(tcs, results)
    assert tc.total == 5
    assert tc.executed == 4  # 3 PASS + 1 FAIL
    assert tc.passed == 3
    assert tc.failed == 1
    assert tc.skipped == 1
    by = {c.category: c for c in tc.by_category}
    assert by["BOUNDARY"].executed == 2
    assert by["NEGATIVE"].executed == 1
    assert by["EQUIVALENCE"].skipped == 1
    assert by["POSITIVE"].executed == 1


def test_category_pass_rate_and_execution_coverage():
    tcs = [
        make_test_case("TC-1", "REQ-001", TestCategory.POSITIVE),
        make_test_case("TC-2", "REQ-001", TestCategory.POSITIVE),
    ]
    results = [
        make_result("TC-1", "REQ-001", TestStatus.PASS),
        make_result("TC-2", "REQ-001", TestStatus.FAIL),
    ]
    tc = AnalysisService.analyze_test_coverage(tcs, results)
    assert tc.execution_coverage == 100.0
    assert tc.pass_rate == 50.0


def test_empty_results_category_coverage():
    tcs = [make_test_case("TC-1", "REQ-001", TestCategory.POSITIVE)]
    tc = AnalysisService.analyze_test_coverage(tcs, [])
    assert tc.executed == 0
    assert tc.execution_coverage == 0.0
    assert tc.pass_rate == 0.0


# ----------------------------------------------------------------------
# Interface coverage
# ----------------------------------------------------------------------


def test_interface_sensor_and_mqtt_from_metadata():
    tcs = [
        make_test_case("TC-1", "REQ-001", protocol="SENSOR"),
        make_test_case("TC-2", "REQ-001", protocol="SENSOR"),
        make_test_case("TC-3", "REQ-001", protocol="MQTT"),
    ]
    results = [
        make_result("TC-1", "REQ-001", TestStatus.PASS),
        make_result("TC-2", "REQ-001", TestStatus.PASS),
        make_result("TC-3", "REQ-001", TestStatus.SKIPPED),
    ]
    ics = {ic.protocol: ic for ic in
           AnalysisService.analyze_interface_coverage(tcs, results)}
    assert ics["SENSOR"].interface == "Sensor/simulator"
    assert ics["SENSOR"].covered is True
    assert ics["MQTT"].interface == "MQTT"
    assert ics["MQTT"].covered is False  # skipped, not executed
    assert ics["MQTT"].executed == 0
    assert ics["MQTT"].skipped == 1


def test_interface_not_invented_when_no_tests():
    tcs = [make_test_case("TC-1", "REQ-001", protocol="SENSOR")]
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS)]
    ics = AnalysisService.analyze_interface_coverage(tcs, results)
    protocols = {ic.protocol for ic in ics}
    assert protocols == {"SENSOR"}  # no MQTT invented
    assert all(ic.interface in {"Sensor/simulator"} for ic in ics)


def test_interface_results_for_unknown_test_ignored():
    tcs = [make_test_case("TC-1", "REQ-001", protocol="SENSOR")]
    results = [make_result("TC-999", "REQ-X", TestStatus.PASS)]
    ics = AnalysisService.analyze_interface_coverage(tcs, results)
    assert ics[0].executed == 0


# ----------------------------------------------------------------------
# Fault detection + rate
# ----------------------------------------------------------------------


def test_detected_fault_needs_failing_assertion_evidence():
    faults = make_known_faults(FaultType.SENSOR_OUT_OF_RANGE)
    # inject the fault but test PASSES (no assertion catches it) -> missed
    passed = make_result(
        "TC-1", "REQ-001", TestStatus.PASS,
        injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE],
    )
    cov = AnalysisService.analyze_fault_detection([passed], faults)
    assert cov[0].injected_count == 1
    assert cov[0].detected_count == 0
    assert cov[0].missed_count == 1
    assert cov[0].detected is False
    assert cov[0].detection_rate == 0.0


def test_injected_and_detected_fault():
    faults = make_known_faults(FaultType.SENSOR_OUT_OF_RANGE)
    failed = make_result(
        "TC-1", "REQ-001", TestStatus.FAIL,
        injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE],
    )
    cov = AnalysisService.analyze_fault_detection([failed], faults)
    assert cov[0].injected_count == 1
    assert cov[0].detected_count == 1
    assert cov[0].missed_count == 0
    assert cov[0].detected is True
    assert cov[0].detection_rate == 100.0
    assert cov[0].related_test_cases == ["TC-1"]


def test_fault_detection_mixed():
    faults = make_known_faults(FaultType.SENSOR_OUT_OF_RANGE)
    results = [
        make_result("TC-1", "REQ-001", TestStatus.FAIL,
                    injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE]),
        make_result("TC-2", "REQ-001", TestStatus.PASS,
                    injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE]),
    ]
    cov = AnalysisService.analyze_fault_detection(results, faults)
    assert cov[0].injected_count == 2
    assert cov[0].detected_count == 1
    assert cov[0].missed_count == 1
    assert cov[0].detection_rate == 50.0


def test_fault_with_no_injection():
    faults = make_known_faults(FaultType.MQTT_DISCONNECT)
    cov = AnalysisService.analyze_fault_detection([], faults)
    assert cov[0].injected_count == 0
    assert cov[0].detected_count == 0
    assert cov[0].detection_rate == 0.0
    assert cov[0].related_test_cases == []


def test_fault_detection_rate_zero_safe():
    faults = make_known_faults(FaultType.MQTT_DISCONNECT)
    fc = AnalysisService.analyze_fault_detection([], faults)[0]
    summary = AnalysisService.generate_summary([], _empty_test_coverage(), [fc], 0)
    assert summary.fault_detection_rate == 0.0
    assert summary.total_faults == 1
    assert summary.detected_faults == 0


def test_fault_untested_type_ignored():
    known = make_known_faults(FaultType.DUPLICATE_MESSAGE)
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS,
                           injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE])]
    cov = AnalysisService.analyze_fault_detection(results, known)
    # DUPLICATE_MESSAGE was never injected -> no related tests, missed 0
    assert cov[0].injected_count == 0


# ----------------------------------------------------------------------
# Gap detection
# ----------------------------------------------------------------------


def test_gap_generated_not_executed():
    req = make_requirement("REQ-001")
    executed = make_test_case("TC-1", "REQ-001")
    unexecuted = make_test_case("TC-2", "REQ-001")
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS)]
    gaps = AnalysisService.identify_gaps([req], [executed, unexecuted], results, [])
    types = {g.type for g in gaps}
    assert "TEST_GENERATED_NOT_EXECUTED" in types


def test_gap_requirement_no_executed_test():
    req = make_requirement("REQ-002")
    tc = make_test_case("TC-1", "REQ-002")
    result = make_result("TC-1", "REQ-002", TestStatus.SKIPPED)
    gaps = AnalysisService.identify_gaps([req], [tc], [result], [])
    assert any(g.type == "REQUIREMENT_NO_EXECUTED_TEST" for g in gaps)


def test_gap_fault_no_test_and_not_detected():
    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-1", "REQ-001")]
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS,
                           injected_fault_types=[FaultType.MQTT_DISCONNECT])]
    faults = make_known_faults(FaultType.MQTT_DISCONNECT)
    gaps = AnalysisService.identify_gaps([req], tcs, results, faults)
    types = {g.type for g in gaps}
    # MQTT_DISCONNECT was injected but the test PASSED -> not detected
    assert "FAULT_NOT_DETECTED" in types


def test_gap_interface_no_executed_test():
    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-MQTT", "REQ-001", protocol="MQTT")]
    results = [make_result("TC-MQTT", "REQ-001", TestStatus.SKIPPED)]
    gaps = AnalysisService.identify_gaps([req], tcs, results, [])
    assert any(g.type == "INTERFACE_NO_EXECUTED_TEST" for g in gaps)


def test_gap_missing_negative_and_boundary():
    req = make_requirement("REQ-001", category=RequirementCategory.RANGE)
    tcs = [make_test_case("TC-1", "REQ-001", TestCategory.POSITIVE)]
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS)]
    gaps = AnalysisService.identify_gaps([req], tcs, results, [])
    types = {g.type for g in gaps}
    assert "BOUNDARY_MISSING" in types
    assert "NEGATIVE_MISSING" in types


def test_gap_only_positive():
    req = make_requirement("REQ-001", category=RequirementCategory.RANGE)
    tcs = [make_test_case("TC-1", "REQ-001", TestCategory.POSITIVE)]
    results = [make_result("TC-1", "REQ-001", TestStatus.PASS)]
    gaps = AnalysisService.identify_gaps([req], tcs, results, [])
    assert any(g.type == "REQUIREMENT_ONLY_POSITIVE" for g in gaps)


def test_no_gaps_when_fully_covered():
    req = make_requirement("REQ-001", category=RequirementCategory.RANGE)
    tcs = [
        make_test_case("TC-1", "REQ-001", TestCategory.POSITIVE),
        make_test_case("TC-2", "REQ-001", TestCategory.BOUNDARY),
        make_test_case("TC-3", "REQ-001", TestCategory.NEGATIVE),
    ]
    results = [
        make_result("TC-1", "REQ-001", TestStatus.PASS),
        make_result("TC-2", "REQ-001", TestStatus.PASS),
        make_result("TC-3", "REQ-001", TestStatus.PASS),
    ]
    gaps = AnalysisService.identify_gaps([req], tcs, results, [])
    assert gaps == []


def test_gap_objects_structured():
    req = make_requirement("REQ-001")
    tc = make_test_case("TC-1", "REQ-001")
    gaps = AnalysisService.identify_gaps([req], [tc], [], [])
    g = next(g for g in gaps if g.type == "TEST_GENERATED_NOT_EXECUTED")
    assert g.gap_id
    assert g.requirement_id == "REQ-001"
    assert g.related_test_case_id == "TC-1"
    assert g.severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert g.recommended_action


# ----------------------------------------------------------------------
# Empty handling + duplicates + traceability
# ----------------------------------------------------------------------


def test_empty_results_full_analysis():
    req = make_requirement("REQ-001")
    tc = make_test_case("TC-1", "REQ-001")
    report = AnalysisService.analyze_execution_results(
        [req], [tc], [], make_known_faults(FaultType.SENSOR_OUT_OF_RANGE)
    )
    s = report.summary
    assert s.requirement_coverage == 0.0
    assert s.execution_coverage == 0.0
    assert s.pass_rate == 0.0
    assert s.fault_detection_rate == 0.0
    assert report.gaps


def test_duplicate_result_ids_aggregate_once_per_result():
    # Two results for the SAME test case should both be counted (each result
    # is a real execution), and the requirement totals reflect both.
    req = make_requirement("REQ-001")
    tc = make_test_case("TC-1", "REQ-001")
    results = [
        make_result("TC-1", "REQ-001", TestStatus.PASS),
        make_result("TC-1", "REQ-001", TestStatus.FAIL),
    ]
    cov = AnalysisService.analyze_requirement_coverage([req], [tc], results)
    assert cov[0].executed == 2
    assert cov[0].passed == 1
    assert cov[0].failed == 1


def test_duplicate_fault_type_across_specs_collapses():
    # Two FaultSpecs of the same type -> one FaultCoverage (type-level).
    faults = make_known_faults(FaultType.SENSOR_OUT_OF_RANGE,
                               FaultType.SENSOR_OUT_OF_RANGE)
    fc = AnalysisService.analyze_fault_detection([], faults)
    assert len(fc) == 1


def test_traceability_requirement_ids_preserved():
    req1 = make_requirement("REQ-001")
    req2 = make_requirement("REQ-002")
    tcs = [
        make_test_case("TC-1", "REQ-001"),
        make_test_case("TC-2", "REQ-002"),
    ]
    results = [
        make_result("TC-1", "REQ-001", TestStatus.PASS),
        make_result("TC-2", "REQ-002", TestStatus.PASS),
    ]
    report = AnalysisService.analyze_execution_results([req1, req2], tcs, results, [])
    rids = {rc.requirement_id for rc in report.requirement_coverage}
    assert rids == {"REQ-001", "REQ-002"}


def test_traceability_fault_related_tests():
    faults = make_known_faults(FaultType.SENSOR_OUT_OF_RANGE)
    results = [
        make_result("TC-1", "REQ-001", TestStatus.FAIL,
                    injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE]),
        make_result("TC-2", "REQ-002", TestStatus.FAIL,
                    injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE]),
    ]
    fc = AnalysisService.analyze_fault_detection(results, faults)[0]
    assert set(fc.related_test_cases) == {"TC-1", "TC-2"}


def test_summary_zero_safe():
    s = AnalysisService.generate_summary([], _empty_test_coverage(), [], 0)
    assert s.requirement_coverage == 0.0
    assert s.execution_coverage == 0.0
    assert s.pass_rate == 0.0
    assert s.fault_detection_rate == 0.0


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _empty_test_coverage():
    from app.analysis.models import TestCoverage
    return TestCoverage(
        total=0, executed=0, passed=0, failed=0, errors=0, skipped=0,
        execution_coverage=0.0, pass_rate=0.0, by_category=[],
    )
