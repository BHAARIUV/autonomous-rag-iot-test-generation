"""
Phase 8 unit tests — the execution service (public API).

Covers:
- execute_action / execute_actions happy path,
- execute_test_case: interpretation + isolated execution + traceability,
- interpretation failure -> structured ERROR result (never a crash),
- batch execution: one failure never stops the batch; accurate summary,
- per-test state isolation (reset_state_between_tests),
- honest SKIPPED conversion when MQTT is unavailable (default policy),
  and ERROR retention when on_mqtt_unavailable="error".
"""

from app.config import Settings
from app.iot.models import SensorConfig
from app.iot.simulator import TemperatureSensorSimulator
from app.llm.models import (
    GenerationMetadata,
    TestCase,
    TestCategory,
    TestData,
    TestPriority,
    TestStep,
)
from app.testing import ExecutionService
from app.testing.actions import make_action, TestActionType
from app.testing.models import ExecutionSummary, TestStatus

_META = GenerationMetadata(
    provider="mock", model="mock", generation_mode="mock",
    prompt_version="v1", timestamp="t",
)


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def _case(cid, steps, *, inputs=None, expected=None):
    return TestCase(
        test_case_id=cid,
        requirement_id="REQ-X",
        title="t",
        objective="o",
        category=TestCategory.POSITIVE,
        priority=TestPriority.MEDIUM,
        preconditions=[],
        test_steps=[TestStep(step_number=i + 1, action=s) for i, s in enumerate(steps)],
        expected_result="ok",
        test_data=TestData(inputs=inputs or {}, expected=expected or {}),
        generation_metadata=_META,
    )


def _service(**overrides):
    return ExecutionService(settings_=_settings(), **overrides)


# ------------------------------------------------------------ execute_action


def test_execute_action_reads_and_passes():
    result = _service().execute_action(make_action(TestActionType.READ_SENSOR))
    assert result.status is TestStatus.PASS
    assert result.steps_passed == 1


def test_execute_actions_chain():
    result = _service().execute_actions(
        [
            make_action(TestActionType.SET_TEMPERATURE, value_c=42.5),
            make_action(TestActionType.READ_SENSOR),
            make_action(TestActionType.ASSERT_VALUE, value=42.5),
        ]
    )
    assert result.status is TestStatus.PASS
    assert result.observed_values["temperature"] == "42.5"


def test_execute_actions_with_invalid_action_is_error():
    from app.testing.actions import TestAction

    bogus = TestAction.model_construct(action="NOT_REAL", params={})
    result = _service().execute_actions([bogus])
    assert result.status is TestStatus.ERROR


# ----------------------------------------------------------- execute_test_case


def test_execute_test_case_full_chain_pass():
    service = _service()
    tc = _case(
        "TC-OK",
        ["Set the device input to the nominal value within the declared operating envelope.",
         "Trigger a measurement.",
         "Observe the reported value and device status."],
        inputs={"input": "25"},
        expected={"status": "OK"},
    )
    result = service.execute_test_case(tc)
    assert result.status is TestStatus.PASS
    assert result.test_case_id == "TC-OK"
    assert result.requirement_id == "REQ-X"
    assert result.duration >= 0.0
    assert result.environment is not None


def test_execute_test_case_interpretation_failure_is_structured_error():
    tc = _case("TC-BAD", ["Do something completely unsupported."])
    result = _service().execute_test_case(tc)
    assert result.status is TestStatus.ERROR
    assert result.execution_evidence[0].action == "INTERPRETATION_FAILED"
    assert "UnsupportedActionError" in result.error_message


def test_execute_test_case_derived_assertion_drives_fail():
    tc = _case("TC-MISS",
               ["Drive the device input to 126 C.", "Trigger a measurement."],
               inputs={"input": "126"}, expected={"status": "VALID"})
    result = _service().execute_test_case(tc)
    assert result.status is TestStatus.FAIL


def test_reset_state_between_tests_isolation():
    service = _service()
    tc1 = _case("TC-A", ["Drive the device input to exactly 10 C.", "Trigger a measurement."],
                inputs={"input": "10"})
    tc2 = _case("TC-B", ["Drive the device input to exactly 80 C.", "Trigger a measurement."],
                inputs={"input": "80"})
    r1 = service.execute_test_case(tc1)
    r2 = service.execute_test_case(tc2)
    assert r1.observed_values["temperature"] == "10"
    assert r2.observed_values["temperature"] == "80"
    assert r1.simulator_state.tick_count == 1  # fresh device per test
    assert r2.simulator_state.tick_count == 1


def test_shared_state_when_reset_disabled():
    service = _service(reset_state_between_tests=False)
    tc1 = _case("TC-A", ["Set the device input to the nominal value within the declared operating envelope.",
                         "Trigger a measurement."], inputs={"input": "10"})
    tc2 = _case("TC-B", ["Trigger a measurement."])
    r1 = service.execute_test_case(tc1)
    r2 = service.execute_test_case(tc2)
    assert r1.simulator_state.tick_count == 1
    assert r2.simulator_state.tick_count == 2  # same shared simulator advanced


def test_custom_make_simulator_used():
    made = []

    def factory():
        made.append(1)
        return TemperatureSensorSimulator(SensorConfig(seed=7))

    service = ExecutionService(settings_=_settings(), make_simulator=factory)
    service.execute_test_case(_case("TC-1", ["Trigger a measurement."]))
    service.execute_test_case(_case("TC-2", ["Trigger a measurement."]))
    assert len(made) == 2


# --------------------------------------------------------------------- batch


def test_batch_never_stops_on_failure_and_summarizes():
    cases = [
        _case("TC-PASS", ["Trigger a measurement."]),
        _case("TC-FAIL", ["Drive the device input to 126 C.", "Trigger a measurement."],
              inputs={"input": "126"}, expected={"status": "VALID"}),
        _case("TC-ERROR", ["Do something completely unsupported."]),
    ]
    results, summary = _service().execute_test_cases(cases)
    assert [r.status for r in results] == [TestStatus.PASS, TestStatus.FAIL, TestStatus.ERROR]
    assert isinstance(summary, ExecutionSummary)
    assert summary.total == 3
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.errors == 1
    assert {d.test_case_id for d in summary.failure_details} == {"TC-FAIL", "TC-ERROR"}


# ------------------------------------------------------------ MQTT skip policy


def test_mqtt_unavailable_default_skips_honestly():
    service = ExecutionService(settings_=_settings(MQTT_BROKER_HOST="127.0.0.1", MQTT_BROKER_PORT=1))
    tc = _case("TC-MQTT", ["Subscribe to the device topic.", "Trigger a device publication."])
    result = service.execute_test_case(tc)
    assert result.status is TestStatus.SKIPPED
    assert "unavailable" in (result.failure_reason or "")


def test_mqtt_unavailable_error_policy_keeps_error():
    service = ExecutionService(
        settings_=_settings(MQTT_BROKER_HOST="127.0.0.1", MQTT_BROKER_PORT=1),
        on_mqtt_unavailable="error",
    )
    tc = _case("TC-MQTT", ["Subscribe to the device topic."])
    result = service.execute_test_case(tc)
    assert result.status is TestStatus.ERROR


def test_invalid_mqtt_policy_rejected():
    import pytest

    with pytest.raises(ValueError):
        ExecutionService(on_mqtt_unavailable="sometimes")