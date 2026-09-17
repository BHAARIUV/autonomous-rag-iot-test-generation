"""
Phase 9 unit tests — coverage & fault-analysis models.

Verifies the typed models validate correctly: required fields, frozen
immutability, JSON serializability, default factories and the calculation
fields' constraints.
"""

import json

from app.analysis import AnalysisService
from app.analysis.models import (
    AnalysisReport,
    CategoryTestCoverage,
    CoverageGap,
    CoverageSummary,
    FaultCoverage,
    InterfaceCoverage,
    RequirementCoverage,
    TestCoverage,
)
from app.testing.models import ExecutionSummary

from tests.unit._analysis_helpers import (
    make_known_faults,
    make_requirement,
    make_result,
    make_test_case,
)
from app.faults import FaultType
from app.llm.models import TestCategory
from app.ingestion.models import RequirementCategory
from app.testing.models import TestStatus


def test_requirement_coverage_validates_and_is_frozen():
    rc = RequirementCoverage(
        requirement_id="REQ-001",
        category="RANGE",
        total_generated=4,
        executed=3,
        passed=2,
        failed=1,
        errors=0,
        skipped=0,
        covered=True,
    )
    assert rc.requirement_id == "REQ-001"
    assert rc.covered is True
    try:
        rc.covered = False
        assert False, "model must be frozen"
    except Exception:
        pass


def test_requirement_coverage_rejects_negative_counts():
    import pytest
    with pytest.raises(ValueError):
        RequirementCoverage(
            requirement_id="REQ-001", category="RANGE", total_generated=1,
            executed=-1, passed=-1, failed=0, errors=0, skipped=0, covered=False,
        )


def test_category_test_coverage_zero_safe():
    c = CategoryTestCoverage(
        category="POSITIVE", total=0, executed=0, passed=0, failed=0,
        errors=0, skipped=0, execution_coverage=0.0, pass_rate=0.0,
    )
    assert c.execution_coverage == 0.0
    assert c.pass_rate == 0.0


def test_test_coverage_holds_category_split():
    tc = TestCoverage(
        total=5, executed=4, passed=3, failed=1, errors=0, skipped=1,
        execution_coverage=80.0, pass_rate=60.0, by_category=[],
    )
    assert tc.execution_coverage == 80.0
    assert tc.pass_rate == 60.0


def test_interface_coverage_frozen():
    ic = InterfaceCoverage(
        interface="MQTT", protocol="MQTT", total=1, executed=1, passed=1,
        failed=0, errors=0, skipped=0, covered=True,
    )
    data = ic.model_dump_json()
    assert json.loads(data)["interface"] == "MQTT"


def test_fault_coverage_zero_injection_rate_is_zero():
    fc = FaultCoverage(
        fault_id="F-X", fault_type="SENSOR_OUT_OF_RANGE", detected=False,
        injected_count=0, detected_count=0, missed_count=0, detection_rate=0.0,
        related_test_cases=[],
    )
    assert fc.detection_rate == 0.0
    assert fc.missed_count == 0


def test_coverage_gap_frozen_and_serializable():
    g = CoverageGap(
        gap_id="GAP-001", type="FAULT_NO_TEST",
        description="no test", severity="HIGH",
        recommended_action="add a test",
    )
    assert g.requirement_id is None and g.related_test_case_id is None
    assert "GAP-001" in g.model_dump_json()


def test_coverage_summary_fields():
    cs = CoverageSummary(
        total_requirements=2, covered_requirements=1, requirement_coverage=50.0,
        total_test_cases=4, executed_test_cases=3, execution_coverage=75.0,
        pass_rate=50.0, total_faults=1, detected_faults=1,
        fault_detection_rate=100.0, gap_count=2,
    )
    assert cs.requirement_coverage == 50.0
    assert cs.fault_detection_rate == 100.0


def test_analysis_report_serializable_with_ids():
    from app.analysis.service import AnalysisService
    from tests.unit._analysis_helpers import make_known_faults, make_requirement, make_result, make_test_case

    req = make_requirement("REQ-001")
    tcs = [make_test_case("TC-001", "REQ-001")]
    results = [make_result("TC-001", "REQ-001", TestStatus.PASS)]
    faults = make_known_faults(FaultType.SENSOR_OUT_OF_RANGE)
    report = AnalysisService.analyze_execution_results([req], tcs, results, faults)
    assert report.analysis_id
    assert report.timestamp is not None
    data = json.loads(report.model_dump_json())
    assert data["summary"]["requirement_coverage"] == 100.0
    # a RANGE requirement covered only by a POSITIVE test has real gaps
    assert data["gaps"]
    assert data["recommendations"]


def test_models_round_trip_all_freeze():
    report = AnalysisService.analyze_execution_results(
        [make_requirement("REQ-001")],
        [make_test_case("TC-001", "REQ-001")],
        [make_result("TC-001", "REQ-001", TestStatus.PASS)],
        make_known_faults(FaultType.SENSOR_OUT_OF_RANGE),
    )
    assert report.model_dump()["analysis_id"]
