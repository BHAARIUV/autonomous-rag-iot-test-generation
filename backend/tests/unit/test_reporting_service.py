"""
Phase 10 — Final Reporting service unit tests.

These build small, deterministic Requirement/TestCase/ExecutionResult/FaultSpec
inputs and assert the traceability links, statuses and writers behave exactly as
defined by Phase 10's evidence rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reporting import models as m
from app.reporting.service import FaultInjection, FinalReportService
from app.faults import FaultType
from tests.unit._analysis_helpers import (
    make_known_faults,
    make_requirement,
    make_result,
    make_test_case,
)
from app.testing.models import TestStatus


def _summary() -> m.FinalTestSummary:
    return m.FinalTestSummary(total=12, passed=12, failed=0, errors=0, skipped=0)


class TestBuildPhaseStatuses:
    def test_all_ten_complete_by_default(self):
        phases = FinalReportService.build_phase_statuses()
        assert len(phases) == 10
        assert all(p.status is m.PhaseStatus.COMPLETE for p in phases)
        assert [p.phase_number for p in phases] == list(range(1, 11))

    def test_pending_beyond_cutoff(self):
        phases = FinalReportService.build_phase_statuses(complete_up_to=7)
        assert all(
            (p.status is m.PhaseStatus.COMPLETE) == (p.phase_number <= 7)
            for p in phases
        )
        assert phases[9].status is m.PhaseStatus.PENDING


class TestBuildTestCaseTraceability:
    def test_links_execution_and_final_status(self):
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result("TC-1", "REQ-1", TestStatus.PASS)
        (trace,) = FinalReportService.build_test_case_traceability([tc], [res])
        assert trace.has_executed is True
        assert trace.final_status == "PASS"
        assert trace.executions[0].execution_id == res.execution_id
        assert trace.executions[0].execution_status == "PASS"

    def test_unexecuted_case(self):
        tc = make_test_case("TC-1", "REQ-1")
        (trace,) = FinalReportService.build_test_case_traceability([tc], [])
        assert trace.has_executed is False
        assert trace.final_status is None
        assert trace.executions == []

    def test_captures_injected_fault_types(self):
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result(
            "TC-1", "REQ-1", TestStatus.FAIL,
            injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE, FaultType.SENSOR_OUT_OF_RANGE],
        )
        (trace,) = FinalReportService.build_test_case_traceability([tc], [res])
        types = trace.executions[0].fault_types_injected
        assert "SENSOR_OUT_OF_RANGE" in types


class TestFaultInjection:
    def test_parses_fault_type_from_expected(self):
        res = make_result(
            "TC-1", "REQ-1", TestStatus.FAIL,
            injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE],
        )
        assert FaultInjection.injected_types(res) == ["SENSOR_OUT_OF_RANGE"]

    def test_uppercases_and_takes_last_token(self):
        assert FaultInjection.injected_types(_result_with_expected("inject mqtt_disconnect")) == [
            "MQTT_DISCONNECT"
        ]

    def test_ignores_non_fault_evidence(self):
        res = make_result("TC-1", "REQ-1", TestStatus.PASS)
        assert FaultInjection.injected_types(res) == []

    def test_requires_at_least_two_tokens(self):
        assert FaultInjection.injected_types(_result_with_expected("FAULT")) == []


class TestBuildFaultTraceability:
    def test_detected_when_injected_and_failed(self):
        faults = make_known_faults(*_ft("SENSOR_OUT_OF_RANGE"))
        res = make_result(
            "TC-1", "REQ-1", TestStatus.FAIL,
            injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE],
        )
        (ftrace,) = FinalReportService.build_fault_traceability([res], faults)
        assert ftrace.injection_status is m.InjectionStatus.INJECTED
        assert ftrace.detection_status is m.FaultDetectionStatus.DETECTED
        assert ftrace.execution_result == "FAIL"
        assert ftrace.related_test_case_ids == ["TC-1"]
        assert "TC-1" in ftrace.injection_evidence

    def test_missed_when_injected_but_not_failed(self):
        faults = make_known_faults(*_ft("SENSOR_OUT_OF_RANGE"))
        res = make_result(
            "TC-1", "REQ-1", TestStatus.PASS,
            injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE],
        )
        (ftrace,) = FinalReportService.build_fault_traceability([res], faults)
        assert ftrace.injection_status is m.InjectionStatus.INJECTED
        assert ftrace.detection_status is m.FaultDetectionStatus.MISSED
        assert ftrace.execution_result == "PASS"

    def test_not_executed_when_never_injected(self):
        faults = make_known_faults(*_ft("MQTT_DISCONNECT"))
        (ftrace,) = FinalReportService.build_fault_traceability([], faults)
        assert ftrace.injection_status is m.InjectionStatus.NOT_EXECUTED
        assert ftrace.detection_status is m.FaultDetectionStatus.NOT_EXECUTED
        assert ftrace.execution_result is None

    def test_detection_rate_never_inferred_without_evidence(self):
        faults = make_known_faults(*_ft("MQTT_DISCONNECT"))
        (ftrace,) = FinalReportService.build_fault_traceability([], faults)
        assert "cannot be inferred" in ftrace.detection_evidence


class TestBuildRequirementTraceability:
    def test_covered_requirement(self):
        req = make_requirement("REQ-1")
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result("TC-1", "REQ-1", TestStatus.PASS)
        (trace,) = FinalReportService.build_requirement_traceability(
            [req], [tc], [res], []
        )
        assert trace.covered is True
        assert trace.has_failing_test is False
        assert trace.missing_execution_evidence is False
        assert len(trace.tests) == 1

    def test_uncovered_requirement_without_execution(self):
        req = make_requirement("REQ-1")
        tc = make_test_case("TC-1", "REQ-1")
        (trace,) = FinalReportService.build_requirement_traceability(
            [req], [tc], [], []
        )
        assert trace.covered is False
        assert trace.missing_execution_evidence is True

    def test_failing_test_flagged(self):
        req = make_requirement("REQ-1")
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result("TC-1", "REQ-1", TestStatus.FAIL)
        (trace,) = FinalReportService.build_requirement_traceability(
            [req], [tc], [res], []
        )
        assert trace.has_failing_test is True
        assert trace.covered is True


class TestBuildFinalSummary:
    def test_populates_aggregates(self):
        faults = make_known_faults(*_ft("SENSOR_OUT_OF_RANGE"))
        req = make_requirement("REQ-1")
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result("TC-1", "REQ-1", TestStatus.PASS)
        from app.analysis import AnalysisService

        analysis = AnalysisService.analyze_execution_results(
            [req], [tc], [res], faults
        ).summary
        gaps = AnalysisService.analyze_execution_results(
            [req], [tc], [res], faults
        ).gaps
        s = FinalReportService.build_final_summary(
            analysis=analysis,
            requirements=[req],
            test_cases=[tc],
            results=[res],
            fault_specs=faults,
            gaps=gaps,
            known_limitations=["lim"],
        )
        assert s.requirement_count == 1
        assert s.executed_test_count == 1
        assert s.passed_count == 1
        assert s.known_limitations == ["lim"]
        assert isinstance(s.recommendations, list)


class TestGenerateFinalReport:
    def test_end_to_end_traceability(self):
        faults = make_known_faults(*_ft("SENSOR_OUT_OF_RANGE"))
        req = make_requirement("REQ-1")
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result(
            "TC-1", "REQ-1", TestStatus.FAIL,
            injected_fault_types=[FaultType.SENSOR_OUT_OF_RANGE],
        )
        report = FinalReportService.generate_final_report(
            requirements=[req],
            test_cases=[tc],
            results=[res],
            fault_specs=faults,
            test_summary=_summary(),
            known_limitations=["lim"],
        )
        assert len(report.phases) == 10
        assert report.requirements[0].covered is True
        assert report.requirements[0].has_failing_test is True
        assert report.faults[0].detection_status is m.FaultDetectionStatus.DETECTED
        assert report.summary.detected_fault_count == 1
        assert report.coverage.pass_rate == 0.0  # 0 passed / 1 total

    def test_generated_timestamp_respected(self):
        from datetime import datetime, timezone

        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        req = make_requirement("REQ-1")
        tc = make_test_case("TC-1", "REQ-1")
        res = make_result("TC-1", "REQ-1", TestStatus.PASS)
        report = FinalReportService.generate_final_report(
            requirements=[req],
            test_cases=[tc],
            results=[res],
            fault_specs=[],
            test_summary=_summary(),
            generated_timestamp=ts,
        )
        assert report.generated_timestamp == ts
        assert report.summary.generated_timestamp == ts


class TestWriters:
    def test_json_report(self, tmp_path: Path):
        report = _mini_report()
        path = FinalReportService.write_json_report(report, tmp_path / "rep.json")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["_schema"] == "autonomous-rag-iot-final-report/v1"
        assert data["project_id"] == "autonomous-rag-iot-test-generation"

    def test_markdown_report(self, tmp_path: Path):
        report = _mini_report()
        path = FinalReportService.write_markdown_report(report, tmp_path / "rep.md")
        text = path.read_text(encoding="utf-8")
        assert path.exists()
        assert "Phase Completion" in text
        assert "Coverage Gaps" in text
        assert "Recommendations" in text


def _mini_report() -> m.FinalProjectReport:
    req = make_requirement("REQ-1")
    tc = make_test_case("TC-1", "REQ-1")
    res = make_result("TC-1", "REQ-1", TestStatus.PASS)
    faults: list = []
    return FinalReportService.generate_final_report(
        requirements=[req],
        test_cases=[tc],
        results=[res],
        fault_specs=faults,
        test_summary=_summary(),
        known_limitations=["lim"],
    )


def _result_with_expected(expected: str):
    from app.testing.models import (
        EnvironmentSnapshot,
        ExecutionResult,
        SimulatorStateSnapshot,
        StepEvidence,
        StepOutcome,
    )

    return ExecutionResult(
        test_case_id="TC-1",
        requirement_id="REQ-1",
        status=TestStatus.FAIL,
        steps_executed=1,
        steps_passed=0,
        steps_failed=1,
        failure_reason="x",
        error_message=None,
        execution_evidence=[
            StepEvidence(
                step_number=1,
                action="INJECT_FAULT",
                source_step_text="Inject.",
                action_result=StepOutcome.OK,
                expected=expected,
                observed="active",
            )
        ],
        environment=EnvironmentSnapshot(),
        simulator_state=SimulatorStateSnapshot(
            device_name="Temperature Sensor",
            status=None,
            tick_count=0,
            min_temperature_c=-40.0,
            max_temperature_c=125.0,
            accuracy_c=0.5,
            seed=1,
        ),
        mqtt_information=None,
    )


def _ft(value: str):
    from app.faults import FaultType

    return [FaultType(value)]
