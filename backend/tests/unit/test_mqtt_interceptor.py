"""
Phase 4 unit tests for FaultInjectingPublisher (the MQTT transport fault
interceptor). Uses a stub connection that records publishes, plus a real
Phase 2 simulator — no MQTT broker required.
"""

import time

import pytest

from app.config import settings
from app.faults import FaultInjector, make_fault
from app.faults.models import FaultParams, FaultType, InjectionCondition
from app.faults.mqtt_interceptor import FaultInjectingPublisher
from app.faults.simulator_adapter import FaultInjectedSimulator
from app.iot.mqtt_messages import (
    MessageValidationError,
    deserialize_message,
    reading_to_mqtt_message,
    serialize_message,
)
from app.iot.mqtt_publisher import SensorMqttPublisher
from app.iot.models import SensorConfig
from app.iot.simulator import TemperatureSensorSimulator


class _StubConnection:
    """Minimal stand-in for MqttConnection: records every publish call."""

    def __init__(self):
        self.published = []
        self.is_connected = True

    def publish(self, topic, payload, qos=None):
        self.published.append((topic, payload))
        return True


_config = SensorConfig(min_temperature_c=0.0, max_temperature_c=50.0, base_temperature_c=25.0, seed=1)


def _make_pub(seed=1, sensor_id="stub-sensor"):
    injector = FaultInjector()
    sim = FaultInjectedSimulator(TemperatureSensorSimulator(_config.model_copy(update={"seed": seed})), injector)
    stub = _StubConnection()
    publisher = FaultInjectingPublisher(sim, stub, injector, sensor_id=sensor_id)
    return publisher, stub, injector, sim


def _temperature_payloads(stub):
    return [p for topic, p in stub.published if topic == settings.mqtt_topic_temperature]


def test_normal_path_matches_standard_publisher_byte_for_byte():
    pub, stub, _, _ = _make_pub(seed=11)
    pub.publish_n_readings(3)

    plain_stub = _StubConnection()
    plain = SensorMqttPublisher(
        TemperatureSensorSimulator(_config.model_copy(update={"seed": 11})),
        plain_stub,
        sensor_id="stub-sensor",
    )
    plain.publish_n_readings(3)

    assert stub.published == plain_stub.published


def test_missing_message_drops_publish_but_ticks_simulator():
    pub, stub, injector, sim = _make_pub()
    injector.inject(
        make_fault(
            FaultType.MISSING_MESSAGE,
            injection_condition=InjectionCondition(start_tick=1, end_tick=2),
        )
    )

    pub.publish_n_readings(3)

    # Message index 1 is suppressed: only 2 payloads on the temperature topic.
    assert len(_temperature_payloads(stub)) == 2
    assert sim.tick_count == 3  # simulator still produced all 3 readings
    records = [r for r in injector.history if r.fault_type is FaultType.MISSING_MESSAGE]
    assert len(records) == 1
    assert records[0].tick_index == 1


def test_duplicate_message_publishes_extra_copies():
    pub, stub, injector, _ = _make_pub()
    injector.inject(
        make_fault(
            FaultType.DUPLICATE_MESSAGE,
            params=FaultParams(duplicate_count=2),
            injection_condition=InjectionCondition(start_tick=0, end_tick=1),
        )
    )

    pub.publish_reading()

    payloads = _temperature_payloads(stub)
    assert len(payloads) == 3  # original + 2 extra copies
    assert payloads[0] == payloads[1] == payloads[2]
    assert injector.count_for(next(r.fault_id for r in injector.history)) == 1


def test_delayed_message_applies_delay():
    pub, stub, injector, _ = _make_pub()
    injector.inject(
        make_fault(
            FaultType.DELAYED_MESSAGE,
            params=FaultParams(delay_seconds=0.2),
            injection_condition=InjectionCondition(start_tick=0, end_tick=1),
        )
    )

    started = time.monotonic()
    pub.publish_reading()
    elapsed = time.monotonic() - started

    assert elapsed >= 0.15  # sleep(0.2) happened: keep a generous tolerance
    assert len(_temperature_payloads(stub)) == 1
    assert [r.tick_index for r in injector.history[0:1]] == [0]


def test_invalid_payload_malformed_json_is_rejected_by_deserializer():
    pub, stub, _, _ = _make_pub()
    pub.injector.inject(
        make_fault(
            FaultType.INVALID_PAYLOAD,
            params=FaultParams(invalid_payload_kind="malformed_json"),
        )
    )

    pub.publish_reading()

    bad = _temperature_payloads(stub)[0]
    with pytest.raises(MessageValidationError):
        deserialize_message(bad)


def test_invalid_payload_not_json_bytes_is_rejected_by_deserializer():
    pub, stub, _, _ = _make_pub()
    pub.injector.inject(
        make_fault(
            FaultType.INVALID_PAYLOAD,
            params=FaultParams(invalid_payload_kind="not_json"),
        )
    )

    pub.publish_reading()

    bad = _temperature_payloads(stub)[0]
    assert isinstance(bad, bytes)
    with pytest.raises(MessageValidationError):
        deserialize_message(bad)


def test_invalid_payload_wrong_schema_is_rejected_by_deserializer():
    pub, stub, _, _ = _make_pub()
    pub.injector.inject(
        make_fault(
            FaultType.INVALID_PAYLOAD,
            params=FaultParams(invalid_payload_kind="wrong_schema"),
        )
    )

    pub.publish_reading()

    bad = _temperature_payloads(stub)[0]
    with pytest.raises(MessageValidationError):
        deserialize_message(bad)


def test_mqtt_disconnect_suppresses_publish():
    pub, stub, injector, sim = _make_pub()
    fault_id = injector.inject(make_fault(FaultType.MQTT_DISCONNECT))

    reading = pub.publish_reading()

    assert len(_temperature_payloads(stub)) == 0
    assert reading is not None
    assert sim.tick_count == 1
    assert injector.count_for(fault_id) == 1


def test_mqtt_timeout_suppresses_publish_and_records():
    pub, stub, injector, _ = _make_pub()
    fault_id = injector.inject(make_fault(FaultType.MQTT_TIMEOUT))

    pub.publish_reading()

    assert len(_temperature_payloads(stub)) == 0
    assert len(injector.history) == 1
    assert injector.history[0].fault_id == fault_id
    assert "timeout" in injector.history[0].detail.lower()


def test_transport_faults_stay_within_window_and_deactivation_resumes():
    pub, stub, injector, _ = _make_pub()
    fault_id = injector.add_fault(
        make_fault(
            FaultType.MQTT_DISCONNECT,
            injection_condition=InjectionCondition(start_tick=1, end_tick=2),
        )
    )
    injector.activate(fault_id)

    pub.publish_n_readings(3)  # index 1 suppressed only

    assert len(_temperature_payloads(stub)) == 2

    injector.deactivate(fault_id)
    pub.publish_reading()

    assert len(_temperature_payloads(stub)) == 3


def test_message_index_reset():
    pub, stub, _, _ = _make_pub()
    pub.publish_reading()
    assert pub.message_index == 1
    pub.reset()
    assert pub.message_index == 0
    pub.publish_reading()
    assert pub.message_index == 1