"""
Phase 8 — structured, strongly-typed test actions.

WHY (SECURITY):
    Generated test specifications are UNTRUSTED input. The executor never
    interprets free-form code: execution is driven ONLY by this closed set
    of structured actions. Unknown action types and malformed parameters are
    rejected by typed validation before anything touches the simulator, the
    broker, or the fault engine.

WHAT:
    - `TestActionType` — the 13 supported action kinds (enum, closed set).
    - One frozen parameter model per action (`extra="forbid"` so unknown
      parameter keys are rejected, not ignored).
    - `TestAction` — `{action: TestActionType, params: {...}}`, the wire-safe
      shape used by tests/demo/executor.
    - `validate_action(action)` — resolves `params` against the typed model
      for that action and raises `UnknownActionError` /
      `InvalidActionParameterError` on anything unsupported.

HOW:
    Each action maps to a dedicated handler in `executor.py`. Actions reuse
    the existing Phase 2-4 building blocks (sensor status, MQTT publisher /
    subscriber primitives, the Phase 4 `FaultRegistry`/`make_fault`).

HOW TO VERIFY:
    See tests/unit/test_execution_actions.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.faults.models import FaultType
from app.iot.models import SensorStatus
from app.testing.errors import InvalidActionParameterError, UnknownActionError


class TestActionType(str, Enum):
    """The closed set of actions the executor may perform."""

    SET_SENSOR_STATUS = "SET_SENSOR_STATUS"
    SET_TEMPERATURE = "SET_TEMPERATURE"
    READ_SENSOR = "READ_SENSOR"
    WAIT = "WAIT"
    MQTT_PUBLISH = "MQTT_PUBLISH"
    MQTT_SUBSCRIBE = "MQTT_SUBSCRIBE"
    INJECT_FAULT = "INJECT_FAULT"
    CLEAR_FAULT = "CLEAR_FAULT"
    ASSERT_VALUE = "ASSERT_VALUE"
    ASSERT_RANGE = "ASSERT_RANGE"
    ASSERT_STATUS = "ASSERT_STATUS"
    ASSERT_MESSAGE = "ASSERT_MESSAGE"
    RESET_SIMULATOR = "RESET_SIMULATOR"


# ---------------------------------------------------------------------------
# Typed parameter models (one per action, extra keys rejected)
# ---------------------------------------------------------------------------


class ParamModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SetSensorStatusParams(ParamModel):
    status: SensorStatus


class SetTemperatureParams(ParamModel):
    value_c: float = Field(description="Commanded sensor output value in degrees C")
    unit: str = Field(default="C", pattern="^C$", description="Only Celsius is supported")


class ReadSensorParams(ParamModel):
    pass


class WaitParams(ParamModel):
    seconds: float = Field(ge=0.0, description="Seconds to hold (capped by config)")


class MqttPublishParams(ParamModel):
    topic: str | None = Field(
        default=None, description="Defaults to the configured temperature topic"
    )
    payload: str | None = Field(
        default=None, description="Explicit payload; None = publish the last observed reading"
    )
    qos: int = Field(default=1, ge=0, le=2)


class MqttSubscribeParams(ParamModel):
    topic: str | None = Field(
        default=None, description="Topic to observe; defaults to configured topics"
    )
    topics: list[str] = Field(default_factory=list, description="Multiple topics")


class InjectFaultParams(ParamModel):
    fault_type: FaultType
    severity: str | None = Field(default=None, description="Optional canonical severity override")
    overshoot_c: float = Field(default=10.0, ge=0.0, description="SENSOR_OUT_OF_RANGE delta")
    undershoot_c: float = Field(default=10.0, ge=0.0, description="SENSOR_UNDER_RANGE delta")
    invalid_data_kind: str = Field(
        default="nan", pattern="^(nan|inf)$", description="INVALID_SENSOR_DATA kind"
    )
    delay_seconds: float = Field(default=1.0, ge=0.0, description="DELAYED_MESSAGE delay")
    duplicate_count: int = Field(default=1, ge=1, le=10, description="DUPLICATE_MESSAGE extras")
    invalid_payload_kind: str = Field(
        default="malformed_json",
        pattern="^(malformed_json|not_json|wrong_schema)$",
        description="INVALID_PAYLOAD corruption kind",
    )
    start_tick: int = Field(default=0, ge=0, description="Fault window start index")
    end_tick: int | None = Field(default=None, ge=1, description="Fault window exclusive end")
    every_n: int | None = Field(default=None, ge=1, description="Periodic firing within window")


class ClearFaultParams(ParamModel):
    fault_id: str | None = Field(
        default=None, description="Fault to clear; None clears every active fault"
    )


class AssertValueParams(ParamModel):
    value: float | str = Field(description="Expected value")
    tolerance: float = Field(default=1e-6, ge=0.0, description="Allowed absolute deviation")


class AssertRangeParams(ParamModel):
    low: float | None = Field(default=None, description="Inclusive lower bound; None = device min")
    high: float | None = Field(default=None, description="Inclusive upper bound; None = device max")


class AssertStatusParams(ParamModel):
    status: SensorStatus | None = Field(default=None, description="Expected ONLINE/OFFLINE")
    valid: bool | None = Field(default=None, description="Expected valid flag, if relevant")


class AssertMessageParams(ParamModel):
    topic: str | None = Field(default=None, description="Topic to check (default configured)")
    field: str | None = Field(
        default=None, description="Message field to compare (sensor_id/status/valid/temperature)"
    )
    equals: str | float | bool | None = Field(default=None, description="Expected field value")
    min_count: int = Field(default=1, ge=1, description="Minimum number of received messages")
    wait_seconds: float = Field(
        default=2.0, ge=0.0, description="Bounded wait for the message (capped by config)"
    )


class ResetParams(ParamModel):
    pass


# action type -> its typed parameter model
PARAM_MODEL_BY_ACTION: dict[TestActionType, type[ParamModel]] = {
    TestActionType.SET_SENSOR_STATUS: SetSensorStatusParams,
    TestActionType.SET_TEMPERATURE: SetTemperatureParams,
    TestActionType.READ_SENSOR: ReadSensorParams,
    TestActionType.WAIT: WaitParams,
    TestActionType.MQTT_PUBLISH: MqttPublishParams,
    TestActionType.MQTT_SUBSCRIBE: MqttSubscribeParams,
    TestActionType.INJECT_FAULT: InjectFaultParams,
    TestActionType.CLEAR_FAULT: ClearFaultParams,
    TestActionType.ASSERT_VALUE: AssertValueParams,
    TestActionType.ASSERT_RANGE: AssertRangeParams,
    TestActionType.ASSERT_STATUS: AssertStatusParams,
    TestActionType.ASSERT_MESSAGE: AssertMessageParams,
    TestActionType.RESET_SIMULATOR: ResetParams,
}


class TestAction(BaseModel):
    """One structured, strongly-typed action to execute."""

    model_config = ConfigDict(frozen=True)

    action: TestActionType
    params: dict[str, Any] = Field(default_factory=dict)

    def validate(self) -> Any:
        """Resolve and validate this action's params against its typed model.

        Raises:
            UnknownActionError / InvalidActionParameterError — never executes.
        """
        return validate_action(self)


def validate_action(action: TestAction) -> Any:
    """Validate a TestAction; returns the frozen, typed params for its type."""
    if not isinstance(action.action, TestActionType):
        raise UnknownActionError(f"Unsupported action type: {action.action!r}")

    param_model = PARAM_MODEL_BY_ACTION.get(action.action)
    if param_model is None:
        raise UnknownActionError(f"No parameter model registered for {action.action}")

    if action.params is None:
        action_params: dict = {}
    elif isinstance(action.params, dict):
        action_params = action.params
    else:
        raise InvalidActionParameterError(
            f"params for '{action.action}' must be an object, got {type(action.params).__name__}"
        )

    try:
        return param_model.model_validate(action_params)
    except Exception as exc:  # pydantic ValidationError (field-level)
        raise InvalidActionParameterError(
            f"Invalid parameters for '{action.action}': {exc}"
        ) from exc


def make_action(action_type: TestActionType, **params) -> TestAction:
    """Build + validate a TestAction in one call (raises on invalid input)."""
    action = TestAction(action=action_type, params=params)
    action.validate()
    return action