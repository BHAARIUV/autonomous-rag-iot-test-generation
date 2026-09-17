"""
Phase 8 unit tests — the controlled test-action interpreter.

Covers:
- the exact prose vocabulary emitted by the Phase 7 mock provider and the
  structured actions it maps to (closed grammar, deterministic),
- rejection of unsupported test steps (UnsupportedActionError),
- terminal assertions derived from test_data.expected.
"""

import pytest

from app.llm.models import (
    GenerationMetadata,
    TestCase,
    TestCategory,
    TestData,
    TestPriority,
    TestStep,
)
from app.testing.actions import TestActionType
from app.testing.errors import UnsupportedActionError
from app.testing.interpreter import interpret_step, interpret_test_case

_META = GenerationMetadata(
    provider="mock", model="mock", generation_mode="mock",
    prompt_version="v1", timestamp="t",
)


def _case(steps, *, inputs=None, expected=None):
    return TestCase(
        test_case_id="TC-001",
        requirement_id="REQ-001",
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


def test_interpret_step_uses_inputs_before_text():
    td = TestData(inputs={"input": "25"}, expected={})
    actions = interpret_step(
        "Set the device input to the nominal value within the declared operating envelope.",
        test_data=td,
    )
    assert len(actions) == 1
    assert actions[0].action is TestActionType.SET_TEMPERATURE
    assert actions[0].params["value_c"] == 25.0


def test_interpret_step_drives_input_to_exact_number():
    actions = interpret_step("Drive the device input to exactly -40 C.")
    assert actions[0].action is TestActionType.SET_TEMPERATURE
    assert actions[0].params["value_c"] == -40.0


def test_interpret_step_negative_value_from_text():
    actions = interpret_step("Drive the device input to -40.1 C, below the minimum.")
    assert actions[0].params["value_c"] == -40.1


def test_interpret_step_deviation_uses_deviation_input():
    td = TestData(inputs={"deviation": "+0.5"}, expected={})
    actions = interpret_step("Set up a deviation of +0.5 C from the true value.", test_data=td)
    assert actions[0].params["value_c"] == 0.5


def test_interpret_step_reads():
    for text in [
        "Trigger a measurement.",
        "Observe the reported value and device status.",
        "Trigger a measurement and read the result.",
        "Trigger a measurement and check the device response.",
        "Confirm a fresh measurement was produced.",
        "Exercise the device through its normal operating path.",
    ]:
        actions = interpret_step(text)
        assert actions[0].action is TestActionType.READ_SENSOR, text


def test_interpret_step_offline_and_recovery():
    a = interpret_step("Take the device offline / disconnect it from the network.")
    assert a[0].action is TestActionType.SET_SENSOR_STATUS
    assert a[0].params["status"] == "OFFLINE"
    b = interpret_step("Bring the network back and observe reconnection.")
    assert b[0].action is TestActionType.SET_SENSOR_STATUS
    assert b[0].params["status"] == "ONLINE"


def test_interpret_step_wait_uses_interval_input():
    td = TestData(inputs={"interval_s": "1"}, expected={})
    actions = interpret_step("Wait one declared interval (1 s).", test_data=td)
    assert actions[0].action is TestActionType.WAIT
    assert actions[0].params["seconds"] == 1.0


def test_interpret_step_mqtt_subscribe():
    actions = interpret_step("Subscribe to the device topic.")
    assert actions[0].action is TestActionType.MQTT_SUBSCRIBE


def test_interpret_step_mqtt_publish():
    actions = interpret_step("Trigger a device publication.")
    assert actions[0].action is TestActionType.MQTT_PUBLISH


def test_interpret_step_validate_received():
    actions = interpret_step("Validate the received JSON payload against the expected schema.")
    assert actions[0].action is TestActionType.ASSERT_MESSAGE
    assert actions[0].params["field"] == "valid"
    assert actions[0].params["equals"] is True


def test_interpret_step_qos_publish_subscribes_then_asserts():
    actions = interpret_step("Publish a message with QoS 1.")
    assert [a.action for a in actions] == [
        TestActionType.MQTT_SUBSCRIBE,
        TestActionType.MQTT_PUBLISH,
        TestActionType.ASSERT_MESSAGE,
    ]
    assert actions[1].params["qos"] == 1


def test_interpret_step_confirms_puback():
    actions = interpret_step("Confirm the PUBACK / delivery acknowledgement.")
    assert actions[0].action is TestActionType.ASSERT_MESSAGE
    assert actions[0].params["min_count"] == 1


def test_interpret_step_malformed_payload_is_literal_data():
    actions = interpret_step("Send a payload with a wrong field type / missing field.")
    assert actions[0].action is TestActionType.MQTT_PUBLISH
    payload = actions[0].params["payload"]
    assert isinstance(payload, str) and "not-a-number" in payload


def test_interpret_step_reset_clock():
    actions = interpret_step("Start the sampling clock.")
    assert actions[0].action is TestActionType.RESET_SIMULATOR


def test_interpret_step_rejects_unsupported_prose():
    with pytest.raises(UnsupportedActionError):
        interpret_step("Do something completely unsupported.")
    with pytest.raises(UnsupportedActionError):
        interpret_step("   ")


@pytest.mark.parametrize(
    "expected,expected_action",
    [
        ({"status": "VALID"}, TestActionType.ASSERT_STATUS),
        ({"status": "INVALID", "reason": "BELOW_MIN"}, TestActionType.ASSERT_STATUS),
        ({"status": "VALID", "edge": "MIN"}, TestActionType.ASSERT_RANGE),
        ({"status": "VALID", "edge": "MAX"}, TestActionType.ASSERT_RANGE),
        ({"partition": "VALID"}, TestActionType.ASSERT_RANGE),
        ({"status": "OK"}, TestActionType.ASSERT_STATUS),
        ({"result": "SUCCESS"}, TestActionType.ASSERT_STATUS),
        ({"received": "CONFORMANT"}, TestActionType.ASSERT_MESSAGE),
        ({"delivery": "AT_LEAST_ONCE"}, TestActionType.ASSERT_MESSAGE),
    ],
)
def test_derived_terminal_assertion(expected, expected_action):
    case = _case(["Trigger a measurement."], expected=expected)
    actions = interpret_test_case(case)
    assert actions[-1].action is expected_action
    if expected_action is TestActionType.ASSERT_STATUS and expected.get("status") in {"VALID", "INVALID"}:
        assert actions[-1].params["valid"] in (True, False)


def test_derived_assert_range_uses_device_bounds_by_default():
    case = _case(["Drive the device input to exactly -40 C.", "Trigger a measurement."],
                 inputs={"input": "-40"}, expected={"status": "VALID", "edge": "MIN"})
    actions = interpret_test_case(case)
    assert actions[-1].action is TestActionType.ASSERT_RANGE
    assert actions[-1].params.get("low") is None
    assert actions[-1].params.get("high") is None


def test_interpret_test_case_rejects_non_testcase():
    with pytest.raises(UnsupportedActionError):
        interpret_test_case({"test_steps": [], "test_data": {}})


def test_interpret_test_case_full_mock_suite_case():
    case = _case(
        [
            "Set the device input to the nominal value within the declared operating envelope.",
            "Trigger a measurement.",
            "Observe the reported value and device status.",
        ],
        inputs={"input": "42.5"},
        expected={"status": "OK"},
    )
    actions = interpret_test_case(case)
    assert [a.action for a in actions] == [
        TestActionType.SET_TEMPERATURE,
        TestActionType.READ_SENSOR,
        TestActionType.READ_SENSOR,
        TestActionType.ASSERT_STATUS,
    ]


def test_interpret_test_case_appends_expected_when_present():
    case = _case(["Trigger a measurement."], expected={"status": "OK"})
    actions = interpret_test_case(case)
    assert len(actions) == 2
    assert actions[-1].params["status"] == "ONLINE"


def test_interpret_test_case_no_derived_assertion_without_expected():
    case = _case(["Trigger a measurement."], expected={})
    actions = interpret_test_case(case)
    assert len(actions) == 1