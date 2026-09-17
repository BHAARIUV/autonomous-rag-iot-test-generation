"""
Phase 8 unit tests — the controlled test-action executor.

Covers (against a real deterministic Phase 2 simulator):
- READ/SET/WAIT/RESET/status semantics and observed-values aggregation,
- deterministic reproducibility,
- FAIL (assertion not met) distinct from ERROR (execution failed),
- fault injection via the shared Phase 4 engine (and CLEAR_FAULT),
- WAIT-cap rejection and the wall-clock ExecutionTimeoutError,
- MQTT actions failing with MqttUnavailableError on an unreachable broker
  (never a fake pass).
"""

import pytest

from app.config import Settings
from app.iot.models import SensorStatus
from app.iot.simulator import TemperatureSensorSimulator
from app.testing.actions import make_action, TestActionType
from app.testing.errors import ExecutionTimeoutError
from app.testing.executor import TestExecutor
from app.testing.models import StepOutcome, TestStatus


def _settings(**overrides):
    return Settings(_env_file=None, **overrides)


def _new_executor(**overrides):
    kwargs: dict = {"settings_": _settings()}
    kwargs.setdefault("simulator", TemperatureSensorSimulator())
    kwargs.update(overrides)
    return TestExecutor(**kwargs)


def _run(actions, **executor_overrides):
    ex = _new_executor(**executor_overrides)
    return ex.execute(actions, test_case_id="TC-EX", requirement_id="REQ-EX")


def test_single_read_is_pass_with_evidence():
    result = _run([make_action(TestActionType.READ_SENSOR)])
    assert result.status is TestStatus.PASS
    assert result.steps_executed == 1
    assert result.steps_passed == 1
    assert result.execution_evidence[0].action == "READ_SENSOR"
    assert result.simulator_state.tick_count == 1
    assert result.observed_values["temperature"]


def test_deterministic_reproducibility():
    acts = [make_action(TestActionType.READ_SENSOR) for _ in range(3)]
    a = _run(acts).observed_values["temperature"]
    b = _run(acts).observed_values["temperature"]
    assert a == b


def test_set_temperature_commands_subsequent_read():
    result = _run([
        make_action(TestActionType.SET_TEMPERATURE, value_c=42.5),
        make_action(TestActionType.READ_SENSOR),
    ])
    assert result.status is TestStatus.PASS
    assert result.observed_values["temperature"] == "42.5"
    assert result.simulator_state.commanded_value == 42.5


def test_out_of_range_command_reports_invalid():
    result = _run([
        make_action(TestActionType.SET_TEMPERATURE, value_c=126.0),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_STATUS, valid=False),
    ])
    assert result.status is TestStatus.PASS
    assert result.observed_values["valid"] == "False"


def test_output_of_range_command_fails_assert_valid_true():
    result = _run([
        make_action(TestActionType.SET_TEMPERATURE, value_c=126.0),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_STATUS, valid=True),
    ])
    assert result.status is TestStatus.FAIL
    assert "valid" in result.failure_reason


def test_assert_range_device_bounds():
    result = _run([
        make_action(TestActionType.SET_TEMPERATURE, value_c=-40.0),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_RANGE),
    ])
    assert result.status is TestStatus.PASS
    assert result.observed_values["temperature"] == "-40"


def test_assert_value_fails_when_no_reading_yet():
    result = _run([make_action(TestActionType.ASSERT_VALUE, value=1.0)])
    assert result.status is TestStatus.FAIL
    assert result.failure_reason


def test_sensor_offline_and_recovery():
    offline = _run([
        make_action(TestActionType.SET_SENSOR_STATUS, status="OFFLINE"),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_STATUS, valid=False),
    ])
    assert offline.status is TestStatus.PASS
    assert offline.observed_values["valid"] == "False"
    recovery = _run([
        make_action(TestActionType.SET_SENSOR_STATUS, status="ONLINE"),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_STATUS, valid=True),
    ])
    assert recovery.status is TestStatus.PASS


def test_assert_status_online_after_offline_fails():
    result = _run([
        make_action(TestActionType.SET_SENSOR_STATUS, status="OFFLINE"),
        make_action(TestActionType.ASSERT_STATUS, status="ONLINE"),
    ])
    assert result.status is TestStatus.FAIL


def test_wait_obeys_cap_and_rejects_larger():
    ok = _run([make_action(TestActionType.WAIT, seconds=0.01)])
    assert ok.status is TestStatus.PASS
    over = _run([make_action(TestActionType.WAIT, seconds=60.0)])
    assert over.status is TestStatus.ERROR
    assert "cap" in over.error_message


def test_reset_simulator_clears_command_and_state():
    result = _run([
        make_action(TestActionType.SET_TEMPERATURE, value_c=99.0),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.RESET_SIMULATOR),
        make_action(TestActionType.READ_SENSOR),
    ])
    assert result.status is TestStatus.PASS
    assert result.simulator_state.commanded_value is None
    assert result.simulator_state.tick_count == 1  # fresh sequence after reset


def test_inject_sensor_out_of_range_causes_assert_fail():
    result = _run([
        make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE",
                    start_tick=0),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_RANGE),
    ])
    assert result.status is TestStatus.FAIL
    assert "outside" in result.failure_reason


def test_fault_reading_is_recorded_in_injector_history():
    ex = _new_executor()
    ex.execute([
        make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_UNDER_RANGE",
                    start_tick=0, end_tick=4, every_n=2),
        make_action(TestActionType.READ_SENSOR),  # tick0 fires
        make_action(TestActionType.READ_SENSOR),  # tick1 clean
        make_action(TestActionType.READ_SENSOR),  # tick2 fires
    ])
    records = ex.injector.history
    assert [r.tick_index for r in records] == [0, 2]
    assert all(r.fault_type.value == "SENSOR_UNDER_RANGE" for r in records)


def test_clear_fault_restores_normal_reads():
    result = _run([
        make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE",
                    start_tick=0, end_tick=3),
        make_action(TestActionType.READ_SENSOR),   # faulted
        make_action(TestActionType.CLEAR_FAULT),
        make_action(TestActionType.READ_SENSOR),   # clean
        make_action(TestActionType.ASSERT_RANGE),
    ])
    assert result.status is TestStatus.PASS  # post-clear reading in range


def test_invalid_fault_severity_is_an_error():
    result = _run([
        make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE",
                    severity="EXTREME", start_tick=0),
    ])
    assert result.status is TestStatus.ERROR


def test_unknown_action_type_is_an_error_not_fail():
    from app.testing.actions import TestAction

    bogus = TestAction.model_construct(action="NOPE", params={})
    result = _run([bogus])
    assert result.status is TestStatus.ERROR
    assert result.error_message


def test_timeout_aborts_with_execution_timeout_error(monkeypatch):
    calls = {"n": 0}

    def fake_now():
        calls["n"] += 1
        return 100.0 if calls["n"] >= 2 else 0.0

    monkeypatch.setattr("time.monotonic", fake_now)
    result = _run(
        [make_action(TestActionType.READ_SENSOR), make_action(TestActionType.READ_SENSOR)],
        max_duration_seconds=10.0,
    )
    assert result.status is TestStatus.ERROR
    assert "budget" in (result.error_message or "")
    assert result.execution_evidence[-1].action == "EXECUTION_ABORTED"


def test_mqtt_subscribe_without_broker_is_error_evidence():
    ex = _new_executor(settings_=_settings(MQTT_BROKER_HOST="127.0.0.1", MQTT_BROKER_PORT=1))
    try:
        result = ex.execute(
            [make_action(TestActionType.MQTT_SUBSCRIBE)],
            test_case_id="TC", requirement_id="R",
        )
    finally:
        ex._disconnect_mqtt()
    assert result.status is TestStatus.ERROR
    assert "unavailable" in (result.error_message or "")
    assert any(
        e.action_result is StepOutcome.ERROR and "MQTT" in (e.error_message or "")
        for e in result.execution_evidence
    )


def test_executor_never_runs_without_actions():
    with pytest.raises(Exception):
        _run([])


def test_results_are_frozen_serializable():
    result = _run([make_action(TestActionType.READ_SENSOR)])
    import json

    payload = result.model_dump_json()
    assert '"TC-EX"' in payload
    dumped = json.loads(payload)
    assert dumped["simulator_state"]["tick_count"] == 1


def test_no_simulator_gives_clean_error():
    ex = TestExecutor(settings_=_settings(), simulator=None)
    result = ex.execute(
        [make_action(TestActionType.READ_SENSOR)], test_case_id="TC", requirement_id="R"
    )
    assert result.status is TestStatus.ERROR
    assert result.simulator_state.device_name == "no-simulator"