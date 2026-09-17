"""
Phase 3 unit tests for MQTT message serialization/deserialization and
validation. These are pure unit tests — no MQTT broker involved.
"""

import json

import pytest

from app.iot.models import SensorReading, SensorStatus, utc_epoch_start
from app.iot.mqtt_messages import (
    MessageValidationError,
    SensorMqttMessage,
    deserialize_message,
    reading_to_mqtt_message,
    serialize_message,
)


def _sample_reading(valid: bool = True, status: SensorStatus = SensorStatus.ONLINE) -> SensorReading:
    return SensorReading(
        tick=0,
        timestamp=utc_epoch_start(),
        value_c=25.5,
        status=status,
        valid=valid,
    )


def test_reading_to_mqtt_message_maps_fields_correctly():
    reading = _sample_reading()
    message = reading_to_mqtt_message("temp-sensor-01", reading)

    assert message.sensor_id == "temp-sensor-01"
    assert message.timestamp == reading.timestamp
    assert message.temperature == reading.value_c
    assert message.status == reading.status
    assert message.valid == reading.valid


def test_serialize_then_deserialize_round_trip():
    reading = _sample_reading()
    original = reading_to_mqtt_message("temp-sensor-01", reading)

    payload = serialize_message(original)
    restored = deserialize_message(payload)

    assert restored == original


def test_serialize_produces_valid_json_with_expected_fields():
    reading = _sample_reading()
    message = reading_to_mqtt_message("temp-sensor-01", reading)
    payload = serialize_message(message)

    parsed = json.loads(payload)
    assert set(parsed.keys()) == {"sensor_id", "timestamp", "temperature", "status", "valid"}
    assert parsed["sensor_id"] == "temp-sensor-01"
    assert parsed["temperature"] == 25.5
    assert parsed["status"] == "ONLINE"
    assert parsed["valid"] is True


def test_deserialize_accepts_bytes_payload():
    reading = _sample_reading()
    message = reading_to_mqtt_message("temp-sensor-01", reading)
    payload_bytes = serialize_message(message).encode("utf-8")

    restored = deserialize_message(payload_bytes)
    assert restored == message


def test_deserialize_rejects_malformed_json():
    with pytest.raises(MessageValidationError):
        deserialize_message("{not valid json")


def test_deserialize_rejects_missing_required_field():
    incomplete = json.dumps(
        {
            "sensor_id": "temp-sensor-01",
            "timestamp": "2026-01-01T00:00:00Z",
            "temperature": 25.5,
            # "status" missing
            "valid": True,
        }
    )
    with pytest.raises(MessageValidationError):
        deserialize_message(incomplete)


def test_deserialize_rejects_wrong_type_for_temperature():
    bad_payload = json.dumps(
        {
            "sensor_id": "temp-sensor-01",
            "timestamp": "2026-01-01T00:00:00Z",
            "temperature": "not-a-number",
            "status": "ONLINE",
            "valid": True,
        }
    )
    with pytest.raises(MessageValidationError):
        deserialize_message(bad_payload)


def test_deserialize_rejects_invalid_status_enum_value():
    bad_payload = json.dumps(
        {
            "sensor_id": "temp-sensor-01",
            "timestamp": "2026-01-01T00:00:00Z",
            "temperature": 25.5,
            "status": "SOMETHING_WEIRD",
            "valid": True,
        }
    )
    with pytest.raises(MessageValidationError):
        deserialize_message(bad_payload)


def test_deserialize_rejects_empty_sensor_id():
    bad_payload = json.dumps(
        {
            "sensor_id": "",
            "timestamp": "2026-01-01T00:00:00Z",
            "temperature": 25.5,
            "status": "ONLINE",
            "valid": True,
        }
    )
    with pytest.raises(MessageValidationError):
        deserialize_message(bad_payload)


def test_deserialize_rejects_non_utf8_bytes():
    with pytest.raises(MessageValidationError):
        deserialize_message(b"\xff\xfe\x00\x01")


def test_offline_reading_serializes_and_round_trips():
    """
    An OFFLINE placeholder reading has NaN as its internal value_c, which
    cannot round-trip through JSON — it must be represented as a JSON
    null / Python None on the wire instead, and still round-trip cleanly.
    """
    reading = SensorReading.offline_placeholder(tick=3, timestamp=utc_epoch_start())
    message = reading_to_mqtt_message("temp-sensor-01", reading)
    assert message.temperature is None

    payload = serialize_message(message)
    restored = deserialize_message(payload)

    assert restored.status == SensorStatus.OFFLINE
    assert restored.valid is False
    assert restored.temperature is None


def test_message_is_immutable():
    reading = _sample_reading()
    message = reading_to_mqtt_message("temp-sensor-01", reading)
    with pytest.raises(Exception):
        message.temperature = 99.9  # frozen model must reject mutation
