"""
Phase 8 unit tests — structured, strongly-typed test actions.

Covers:
- the closed action set (13 supported kinds),
- typed parameter validation per action (extra keys forbidden),
- rejection of unknown action types and invalid parameter values,
- make_action / validate_action convenience behaviour.
"""

import pytest
from pydantic import ValidationError

from app.iot.models import SensorStatus
from app.testing.actions import (
    PARAM_MODEL_BY_ACTION,
    TestAction,
    TestActionType,
    make_action,
    validate_action,
)
from app.testing.errors import InvalidActionParameterError, UnknownActionError


def test_closed_action_set_has_13_members():
    assert len(TestActionType) == 13
    assert TestActionType.SET_SENSOR_STATUS.value == "SET_SENSOR_STATUS"
    assert TestActionType.SET_TEMPERATURE.value == "SET_TEMPERATURE"
    assert TestActionType.READ_SENSOR.value == "READ_SENSOR"
    assert TestActionType.WAIT.value == "WAIT"
    assert TestActionType.MQTT_PUBLISH.value == "MQTT_PUBLISH"
    assert TestActionType.MQTT_SUBSCRIBE.value == "MQTT_SUBSCRIBE"
    assert TestActionType.INJECT_FAULT.value == "INJECT_FAULT"
    assert TestActionType.CLEAR_FAULT.value == "CLEAR_FAULT"
    assert TestActionType.ASSERT_VALUE.value == "ASSERT_VALUE"
    assert TestActionType.ASSERT_RANGE.value == "ASSERT_RANGE"
    assert TestActionType.ASSERT_STATUS.value == "ASSERT_STATUS"
    assert TestActionType.ASSERT_MESSAGE.value == "ASSERT_MESSAGE"
    assert TestActionType.RESET_SIMULATOR.value == "RESET_SIMULATOR"


def test_every_action_type_has_a_param_model():
    assert set(PARAM_MODEL_BY_ACTION) == set(TestActionType)


def test_make_action_valid_and_frozen_params():
    action = make_action(TestActionType.SET_TEMPERATURE, value_c=42.5, unit="C")
    assert action.action is TestActionType.SET_TEMPERATURE
    assert action.params["value_c"] == 42.5
    assert TestAction.model_config.get("frozen") is True


def test_validate_action_returns_typed_model():
    params = validate_action(make_action(TestActionType.WAIT, seconds=1.0))
    assert params.seconds == 1.0


def test_unknown_action_type_rejected_before_execution():
    bogus = TestAction.model_construct(action="TURN_OFF_THE_ROOM", params={})
    with pytest.raises(UnknownActionError):
        validate_action(bogus)


def test_action_without_registered_params_rejected():
    action = TestAction(action=TestActionType.READ_SENSOR, params={"bogus": 1})
    with pytest.raises(InvalidActionParameterError):
        validate_action(action)


def test_extra_params_rejected_not_ignored():
    action = make_action(TestActionType.READ_SENSOR)  # valid baseline
    bogus = TestAction(action=TestActionType.READ_SENSOR, params={"extra": True})
    with pytest.raises(InvalidActionParameterError):
        validate_action(bogus)
    assert action.action is TestActionType.READ_SENSOR


def test_wrong_param_types_rejected():
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.WAIT, seconds="soon")  # not numeric


def test_negative_wait_rejected():
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.WAIT, seconds=-0.5)


def test_unit_restricted_to_celsius():
    make_action(TestActionType.SET_TEMPERATURE, value_c=25.0, unit="C")
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.SET_TEMPERATURE, value_c=25.0, unit="F")


def test_mqtt_qos_range_enforced():
    make_action(TestActionType.MQTT_PUBLISH, qos=0)
    make_action(TestActionType.MQTT_PUBLISH, qos=2)
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.MQTT_PUBLISH, qos=3)


def test_assert_message_min_count_ge_one():
    make_action(TestActionType.ASSERT_MESSAGE, min_count=1)
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.ASSERT_MESSAGE, min_count=0)


def test_inject_fault_requires_valid_fault_type():
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.INJECT_FAULT, fault_type="SLAP_THE_SENSOR")


def test_inject_fault_accepts_all_phase4_types():
    from app.faults.models import FaultType

    for fault_type in FaultType:
        t = make_action(TestActionType.INJECT_FAULT, fault_type=fault_type.value,
                        start_tick=0, end_tick=3)
        assert validate_action(t).fault_type is fault_type


def test_set_sensor_status_accepts_enum_or_string():
    a = make_action(TestActionType.SET_SENSOR_STATUS, status="OFFLINE")
    assert validate_action(a).status is SensorStatus.OFFLINE
    b = make_action(TestActionType.SET_SENSOR_STATUS, status=SensorStatus.ONLINE)
    assert validate_action(b).status is SensorStatus.ONLINE
    with pytest.raises(InvalidActionParameterError):
        make_action(TestActionType.SET_SENSOR_STATUS, status="ASLEEP")


def test_test_action_validate_method_surface():
    action = make_action(TestActionType.READ_SENSOR)
    params = action.validate()
    assert params is not None
    with pytest.raises(InvalidActionParameterError):
        TestAction(action=TestActionType.WAIT, params={"seconds": -1}).validate()