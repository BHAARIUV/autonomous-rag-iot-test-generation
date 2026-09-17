"""
Phase 8 — controlled test-action interpreter.

WHY:
    Phase 7 generates TEST SPECIFICATIONS whose steps are natural-language
    prose ('Drive the device input to -40 C.', 'Trigger a measurement.', ...)
    from the mock provider's fixed vocabulary, not structured code. Before
    anything can execute them safely, the prose must be translated into the
    closed set of `TestAction`s — and any step that maps to nothing supported
    must be REJECTED (never guessed, never ignored). Unknown intent produces a
    typed `UnsupportedActionError`, which the execution service turns into an
    ERROR result.

WHAT:
    - interpret_step(step_text, test_data) -> list[TestAction]
        Single-step mapping (ordered, deterministic, first match wins).
    - interpret_test_case(test_case) -> list[TestAction]
        Maps every prose step of a Phase 7 TestCase, then appends ONE terminal
        verification action derived from `test_data.expected` when a literal
        expectation exists, so metadata recorded at generation time still gets
        executed against the device (e.g. 'edge MIN' -> ASSERT_RANGE).

HOW (closed grammar):
    A small, explicit keyword grammar (checked in order) maps each observed
    mock step to exactly one supported action. Literal values come from
    test_data.inputs or the step text itself — never invented, and never
    evaluated as code.

HOW TO VERIFY:
    See tests/unit/test_execution_interpreter.py.
"""

from __future__ import annotations

import re

from app.llm.models import TestCase
from app.testing.actions import TestAction, TestActionType
from app.testing.errors import UnsupportedActionError

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

# Deterministic literal used when a step asks to send a MALFORMED payload
# (data, not code — a fixed string that the subscriber must reject).
_MALFORMED_PAYLOAD = '{"sensor_id": 123, "temperature": "not-a-number", "status": "ONLINE"}'


def _first_number(text: str) -> float | None:
    """First numeric literal present in a step's prose (or None)."""
    match = _NUMBER.search(text)
    return float(match.group(0)) if match else None


def _input_value(test_data, key: str) -> float | None:
    if test_data is None or not test_data.inputs:
        return None
    raw = test_data.inputs.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _set_temperature(value: float | None) -> TestAction:
    if value is None:
        raise UnsupportedActionError("cannot derive a numeric SET_TEMPERATURE value from the test data")
    return TestAction(action=TestActionType.SET_TEMPERATURE, params={"value_c": value, "unit": "C"})


def interpret_step(step_text: str, test_data=None) -> list[TestAction]:
    """Map one prose step to structured actions (closed grammar)."""
    text = (step_text or "").strip().lower()
    if not text:
        raise UnsupportedActionError("test step text is empty")

    # 1. reset -------------------------------------------------------------
    if "reset" in text:
        return [TestAction(action=TestActionType.RESET_SIMULATOR)]

    # 2. offline / device disconnect ---------------------------------------
    if "offline" in text or ("disconnect" in text and (
            "device" in text or "network" in text or "it" in text)):
        return [TestAction(
            action=TestActionType.SET_SENSOR_STATUS, params={"status": "OFFLINE"}
        )]

    # 3. back online / reconnect -------------------------------------------
    if "network back" in text or "reconnect" in text or "go online" in text or " online" in text:
        return [TestAction(
            action=TestActionType.SET_SENSOR_STATUS, params={"status": "ONLINE"}
        )]

    # 4. timing -------------------------------------------------------------
    if "wait" in text:
        seconds = _input_value(test_data, "interval_s")
        if seconds is None:
            seconds = _first_number(text)
        return [TestAction(action=TestActionType.WAIT, params={"seconds": seconds or 1.0})]

    if "start the sampling clock" in text:
        return [TestAction(action=TestActionType.RESET_SIMULATOR)]

    # 5. MQTT delivery (QoS) ------------------------------------------------
    if "publish" in text and "qos" in text:
        # "Publish a message with QoS 1" — to verify delivery we must observe
        # it on the wire, so subscribe first, publish, then assert receipt.
        return [
            TestAction(action=TestActionType.MQTT_SUBSCRIBE),
            TestAction(action=TestActionType.MQTT_PUBLISH, params={"qos": 1}),
            TestAction(action=TestActionType.ASSERT_MESSAGE, params={"min_count": 1}),
        ]

    if "subscribe" in text:
        return [TestAction(action=TestActionType.MQTT_SUBSCRIBE)]

    if "puback" in text or "acknowledg" in text or "delivery acknowledgement" in text:
        return [TestAction(action=TestActionType.ASSERT_MESSAGE, params={"min_count": 1})]

    if "validate the received" in text or "check the received" in text:
        return [TestAction(action=TestActionType.ASSERT_MESSAGE, params={"field": "valid", "equals": True})]

    if "publish" in text or "publication" in text:
        return [TestAction(action=TestActionType.MQTT_PUBLISH)]

    # 6. payload sending (data validation scenarios) -------------------------
    if ("wrong field" in text or "missing field" in text or "malformed" in text) and "payload" in text:
        return [TestAction(
            action=TestActionType.MQTT_PUBLISH, params={"payload": _MALFORMED_PAYLOAD}
        )]
    if "send" in text and "payload" in text:
        return [TestAction(action=TestActionType.MQTT_PUBLISH)]

    # 7. set / drive the input (SET_TEMPERATURE) -----------------------------
    if ("drive the device input" in text or "set" in text
            or "deviation" in text or "boundary value" in text):
        value = _input_value(test_data, "input")
        if value is None:
            value = _input_value(test_data, "deviation")
        if value is None:
            value = _first_number(text)
        return [_set_temperature(value)]

    # 8. assertions ----------------------------------------------------------
    if "assert" in text or "confirm" in text or "check" in text:
        if "gap" in text or "timestamps" in text:
            return [TestAction(action=TestActionType.READ_SENSOR)]
        if "status" in text or "accept" in text or "reject" in text:
            return [TestAction(
                action=TestActionType.ASSERT_STATUS,
                params={"valid": "reject" not in text and "missing" not in text},
            )]
        return [TestAction(action=TestActionType.READ_SENSOR)]

    # 9. measurements / reads -------------------------------------------------
    if (
        "read" in text
        or "measurement" in text
        or "trigger" in text
        or "observe" in text
        or "record" in text
        or "produced" in text
        or "consecutive" in text
        or "response" in text
        or "exercise" in text
        or "sampling clock" in text
        or "normal operating path" in text
    ):
        return [TestAction(action=TestActionType.READ_SENSOR)]

    raise UnsupportedActionError(
        f"step does not map to any supported action: {step_text!r}"
    )


def _expectation_action(test_data) -> TestAction | None:
    """A terminal verification derived from test_data.expected.

    Returns None when no literal expectation is recognizable (the test still
    executes its own steps; it simply has no derived terminal assertion).
    """
    if test_data is None or not test_data.expected:
        return None
    expected = test_data.expected

    edge = (expected.get("edge") or "").upper()
    partition = (expected.get("partition") or "").upper()
    status = (expected.get("status") or "").upper()
    result = (expected.get("result") or "").upper()
    received = (expected.get("received") or "").upper()
    delivery = (expected.get("delivery") or "").upper()

    if edge in {"MIN", "MAX"}:
        return TestAction(action=TestActionType.ASSERT_RANGE)
    if partition == "VALID":
        return TestAction(action=TestActionType.ASSERT_RANGE)
    if status == "VALID":
        return TestAction(action=TestActionType.ASSERT_STATUS, params={"valid": True})
    if status in {"INVALID", "ERROR", "UNKNOWN"}:
        return TestAction(action=TestActionType.ASSERT_STATUS, params={"valid": False})
    if status == "OK" or result == "SUCCESS":
        return TestAction(action=TestActionType.ASSERT_STATUS, params={"status": "ONLINE"})
    if received == "CONFORMANT":
        return TestAction(action=TestActionType.ASSERT_MESSAGE, params={"field": "valid", "equals": True})
    if delivery == "AT_LEAST_ONCE":
        return TestAction(action=TestActionType.ASSERT_MESSAGE, params={"min_count": 1})
    return None


def interpret_test_case(test_case) -> list[TestAction]:
    """Translate a full Phase 7 TestCase into a safe, closed action sequence."""
    if not isinstance(test_case, TestCase):
        raise UnsupportedActionError(
            "expected a Phase 7 TestCase (app.llm.models.TestCase), "
            f"got {type(test_case).__name__}"
        )

    test_data = test_case.test_data
    actions: list[TestAction] = []
    for step in test_case.test_steps:
        actions.extend(interpret_step(step.action, test_data=test_data))

    expectation = _expectation_action(test_data)
    if expectation is not None:
        actions.append(expectation)
    return actions