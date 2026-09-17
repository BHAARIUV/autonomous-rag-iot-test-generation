"""
WHAT:
    The wire-format message used on the `iot/sensor/temperature` MQTT
    topic, plus pure functions to serialize a `SensorReading` into that
    format and to deserialize/validate raw bytes received off MQTT back
    into a structured, trustworthy object.

WHY:
    `SensorReading` (Phase 2, app/iot/models.py) is the simulator's
    internal representation — it has fields like `unit` and `tick` that
    are implementation details of the simulator, not necessarily what
    should go over the wire. Keeping a distinct `SensorMqttMessage`
    schema here means:
      1. The MQTT wire format is explicit and stable, independent of
         internal simulator changes.
      2. A subscriber (which might not be part of this codebase at all —
         e.g. a real dashboard, or a different test client) has one
         clear structured contract to validate against.
      3. Malformed or malicious payloads arriving on the topic (a
         negative test scenario, or Phase 4's "invalid payload" fault)
         are rejected by explicit validation rather than silently
         crashing something downstream.

HOW:
    - `SensorMqttMessage` (Pydantic model): sensor_id, timestamp,
      temperature, status, valid — exactly the fields requested.
    - `reading_to_mqtt_message()`: converts a Phase 2 `SensorReading`
      into this wire schema.
    - `serialize_message()` / `deserialize_message()`: JSON string <->
      `SensorMqttMessage`, with `deserialize_message()` raising a
      `MessageValidationError` (never a raw silent failure) on anything
      malformed — missing fields, wrong types, bad JSON.

HOW TO VERIFY:
    See tests/unit/test_mqtt_messages.py.
"""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, Field, ValidationError

from app.iot.models import SensorReading, SensorStatus


class MessageValidationError(Exception):
    """Raised when raw MQTT payload bytes cannot be parsed into a valid message."""


class SensorMqttMessage(BaseModel):
    """
    Structured payload published on the `iot/sensor/temperature` topic.

    Field set matches the project brief: sensor_id, timestamp,
    temperature, status, valid.

    `temperature` is Optional: standard JSON has no representation for
    NaN, so a NaN value (produced by an OFFLINE placeholder reading, see
    app/iot/models.py) is encoded as JSON `null` on the wire and decoded
    back as `None` here — meaning "no reading available" rather than a
    real numeric value. Consumers must treat `temperature is None` the
    same way they treat `valid is False` / `status == OFFLINE`.
    """

    sensor_id: str = Field(min_length=1)
    timestamp: datetime
    temperature: float | None
    status: SensorStatus
    valid: bool

    model_config = {"frozen": True}


def reading_to_mqtt_message(sensor_id: str, reading: SensorReading) -> SensorMqttMessage:
    """
    Convert an internal Phase-2 SensorReading into the MQTT wire schema.

    A NaN value_c (OFFLINE placeholder readings) is converted to None
    since NaN cannot round-trip through JSON.
    """
    temperature = None if math.isnan(reading.value_c) else reading.value_c
    return SensorMqttMessage(
        sensor_id=sensor_id,
        timestamp=reading.timestamp,
        temperature=temperature,
        status=reading.status,
        valid=reading.valid,
    )


def serialize_message(message: SensorMqttMessage) -> str:
    """Serialize a SensorMqttMessage to a JSON string ready for MQTT publish."""
    return message.model_dump_json()


def deserialize_message(payload: bytes | str) -> SensorMqttMessage:
    """
    Parse and validate raw MQTT payload bytes/string into a
    SensorMqttMessage.

    Raises:
        MessageValidationError: if the payload is not valid JSON, is
        missing required fields, or has fields of the wrong type/shape.
        This is the single validation gate every inbound MQTT message
        must pass through — nothing downstream should trust a payload
        that hasn't come through this function.
    """
    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MessageValidationError(f"Payload is not valid UTF-8: {exc}") from exc

    try:
        return SensorMqttMessage.model_validate_json(payload)
    except ValidationError as exc:
        raise MessageValidationError(f"Invalid MQTT message payload: {exc}") from exc
    except Exception as exc:  # e.g. json.JSONDecodeError bubbled up from pydantic
        raise MessageValidationError(f"Malformed MQTT message payload: {exc}") from exc
