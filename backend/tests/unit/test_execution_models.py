"""
Phase 8 unit tests — execution result models.

Covers:
- TestStatus FAIL/ERROR/SKIPPED distinction (the FAIL-vs-ERROR contract).
- StepEvidence.passed semantics for every outcome combination.
- ExecutionResult traceability (ids present + non-blank) and frozen-ness.
- Environment/simulator/MQTT snapshots.
- ExecutionSummary.from_execution_results aggregation.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.iot.models import SensorStatus
from app.testing.models import (
    EnvironmentSnapshot,
    ExecutionResult,
    ExecutionSummary,
    FailureDetail,
    MqttSnapshot,
    SensorMqttView,
    SimulatorStateSnapshot,
    StepEvidence,
    StepOutcome,
    TestStatus,
)


def test_statuses_are_distinct_values():
    """FAIL and ERROR and SKIPPED must be three different things."""
    assert TestStatus.PASS.value == "PASS"
    assert TestStatus.FAIL.value == "FAIL"
    assert TestStatus.ERROR.value == "ERROR"
    assert TestStatus.SKIPPED.value == "SKIPPED"
    assert TestStatus.FAIL is not TestStatus.ERROR
    assert TestStatus.FAIL is not TestStatus.SKIPPED


def test_step_outcome_values():
    assert {o.value for o in StepOutcome} == {"OK", "FAIL", "ERROR", "SKIPPED"}


def _base_result(**overrides):
    now = datetime.now(timezone.utc)
    defaults = dict(
        test_case_id="TC-001",
        requirement_id="REQ-001",
        status=TestStatus.PASS,
        started_at=now,
        completed_at=now,
        duration=0.5,
        environment=EnvironmentSnapshot(app_env="testing"),
        simulator_state=SimulatorStateSnapshot(
            device_name="Temperature Sensor", status=SensorStatus.ONLINE,
            tick_count=3, min_temperature_c=-40.0, max_temperature_c=125.0,
            accuracy_c=0.5, seed=42,
        ),
    )
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def test_execution_result_holds_traceability_including_evidence():
    evidence = StepEvidence(
        step_number=1, action="READ_SENSOR", action_result=StepOutcome.OK,
        expected="a reading", observed="25.139",
    )
    result = _base_result(
        execution_evidence=[evidence],
        observed_values={"temperature": "25.139"},
        steps_executed=1, steps_passed=1, steps_failed=0,
    )
    assert result.test_case_id == "TC-001"
    assert result.requirement_id == "REQ-001"
    assert len(result.execution_id) == 32  # uuid hex
    assert result.execution_evidence[0].action == "READ_SENSOR"


def test_execution_result_rejects_blank_ids():
    with pytest.raises(ValidationError):
        _base_result(test_case_id="   ")
    with pytest.raises(ValidationError):
        _base_result(requirement_id="")


def test_execution_result_is_frozen():
    result = _base_result()
    with pytest.raises(ValidationError):
        result.status = TestStatus.FAIL


def test_step_evidence_passed_semantics():
    ok = lambda ar: StepEvidence(  # noqa: E731
        step_number=1, action="X", action_result=StepOutcome.OK, assertion_result=ar
    )
    assert ok(None).passed is True
    assert ok(TestStatus.PASS).passed is True
    assert ok(TestStatus.FAIL).passed is False
    err = StepEvidence(step_number=1, action="X", action_result=StepOutcome.ERROR)
    assert err.passed is False
    skip = StepEvidence(step_number=1, action="X", action_result=StepOutcome.SKIPPED)
    assert skip.passed is False
    fail = StepEvidence(step_number=1, action="X", action_result=StepOutcome.FAIL)
    assert fail.passed is False


def test_mqtt_snapshot_shape():
    view = SensorMqttView(
        sensor_id="Temperature Sensor", temperature=42.5,
        status=SensorStatus.ONLINE, valid=True,
    )
    snap = MqttSnapshot(
        available=True, connected=True, broker="localhost:1883",
        topic="iot/sensor/temperature", received_count=1, invalid_count=0,
        last_received=view,
    )
    assert snap.received_count == 1
    assert snap.last_received.temperature == 42.5
    assert snap.last_received.valid is True


def test_fail_carries_failure_reason_error_carries_error_message():
    fail = _base_result(status=TestStatus.FAIL, failure_reason="135 is outside [-40, 125]")
    error = _base_result(status=TestStatus.ERROR, error_message="UnsupportedActionError: nope")
    assert fail.failure_reason and not fail.error_message
    assert error.error_message and not error.failure_reason


def _result(status: TestStatus, cid: str, reason: str = "") -> ExecutionResult:
    return _base_result(test_case_id=cid, status=status, failure_reason=reason)


def test_summary_aggregation_from_results():
    results = [
        _result(TestStatus.PASS, "TC-001"),
        _result(TestStatus.PASS, "TC-002"),
        _result(TestStatus.FAIL, "TC-003", "assertion not met"),
        _result(TestStatus.ERROR, "TC-004", ""),
        _result(TestStatus.SKIPPED, "TC-005", "no broker"),
    ]
    summary = ExecutionSummary.from_execution_results(results)
    assert summary.total == 5
    assert summary.passed == 2
    assert summary.failed == 1
    assert summary.errors == 1
    assert summary.skipped == 1
    assert summary.pass_rate == 40.0


def test_summary_failure_details_exclude_passes():
    results = [_result(TestStatus.PASS, "TC-OK"), _result(TestStatus.FAIL, "TC-BAD", "why")]
    summary = ExecutionSummary.from_execution_results(results)
    assert [d.test_case_id for d in summary.failure_details] == ["TC-BAD"]
    assert summary.failure_details[0].reason == "why"
    assert summary.failure_details[0].status is TestStatus.FAIL


def test_summary_empty_batch():
    summary = ExecutionSummary.from_execution_results([])
    assert summary.total == 0
    assert summary.pass_rate == 0.0
    assert summary.failure_details == []


def test_failure_detail_model_standalone():
    d = FailureDetail(test_case_id="TC-9", status=TestStatus.ERROR, reason="boom",
                      requirement_id="REQ-9")
    assert d.requirement_id == "REQ-9"
    assert d.reason == "boom"