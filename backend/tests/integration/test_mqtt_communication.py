"""
Phase 3 integration tests: real publisher/subscriber communication over
a real, locally running Mosquitto broker (see README "Mosquitto setup").

These tests are deliberately separated from tests/unit/ and are SKIPPED
(not faked, not silently passed) if no broker is reachable on the
configured host/port. This satisfies the requirement: "If Mosquitto is
unavailable, clearly separate broker-dependent tests from pure unit
tests rather than faking successful MQTT communication."

Each test uses a unique MQTT client_id and a fresh topic-free
MqttConnection pair to avoid interference between tests.
"""

import socket
import time
import uuid

import pytest

from app.config import settings
from app.iot.models import SensorConfig
from app.iot.mqtt_client import MqttConnection
from app.iot.mqtt_publisher import SensorMqttPublisher
from app.iot.mqtt_subscriber import SensorMqttSubscriber
from app.iot.simulator import TemperatureSensorSimulator


def _broker_is_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP-level reachability check — does NOT fake an MQTT handshake."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


BROKER_AVAILABLE = _broker_is_reachable(settings.mqtt_broker_host, settings.mqtt_broker_port)

pytestmark = pytest.mark.skipif(
    not BROKER_AVAILABLE,
    reason=(
        f"No MQTT broker reachable at {settings.mqtt_broker_host}:"
        f"{settings.mqtt_broker_port} — start Mosquitto to run these tests "
        f"(see README 'Mosquitto setup')."
    ),
)


def _unique_client_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def subscriber_connection():
    conn = MqttConnection(client_id=_unique_client_id("test-subscriber"))
    conn.connect()
    yield conn
    conn.disconnect()


@pytest.fixture
def publisher_connection():
    conn = MqttConnection(client_id=_unique_client_id("test-publisher"))
    conn.connect()
    yield conn
    conn.disconnect()


def test_connection_reports_connected_after_connect(publisher_connection):
    assert publisher_connection.is_connected is True


def test_disconnect_reports_not_connected():
    conn = MqttConnection(client_id=_unique_client_id("test-disconnect"))
    conn.connect()
    assert conn.is_connected is True
    conn.disconnect()
    assert conn.is_connected is False


def test_publisher_publishes_readings_subscriber_receives_them(
    publisher_connection, subscriber_connection
):
    subscriber = SensorMqttSubscriber(
        subscriber_connection, topics=[settings.mqtt_topic_temperature]
    )
    subscriber.subscribe_all()
    time.sleep(0.3)  # give the broker a moment to register the subscription

    sim = TemperatureSensorSimulator(SensorConfig(seed=99))
    publisher = SensorMqttPublisher(sim, publisher_connection, sensor_id="temp-sensor-test")

    published = publisher.publish_n_readings(5)

    received_in_time = subscriber.wait_for_messages(count=5, timeout=5.0)

    assert received_in_time, (
        f"Expected 5 messages, got {len(subscriber.received_messages)}"
    )
    assert len(subscriber.received_messages) == 5
    assert len(subscriber.invalid_messages) == 0

    # Order should be preserved and values should match what was published.
    for published_reading, received_message in zip(published, subscriber.received_messages):
        assert received_message.sensor_id == "temp-sensor-test"
        assert received_message.temperature == published_reading.value_c
        assert received_message.status == published_reading.status
        assert received_message.valid == published_reading.valid


def test_subscriber_receives_status_topic_updates(publisher_connection, subscriber_connection):
    subscriber = SensorMqttSubscriber(
        subscriber_connection, topics=[settings.mqtt_topic_status]
    )
    subscriber.subscribe_all()
    time.sleep(0.3)

    sim = TemperatureSensorSimulator(SensorConfig(seed=5))
    publisher = SensorMqttPublisher(sim, publisher_connection, sensor_id="temp-sensor-status")
    publisher.publish_n_readings(2)

    received_in_time = subscriber.wait_for_messages(count=2, timeout=5.0)
    assert received_in_time
    assert all(msg.sensor_id == "temp-sensor-status" for msg in subscriber.received_messages)


def test_offline_sensor_publishes_invalid_reading_over_mqtt(
    publisher_connection, subscriber_connection
):
    subscriber = SensorMqttSubscriber(
        subscriber_connection, topics=[settings.mqtt_topic_temperature]
    )
    subscriber.subscribe_all()
    time.sleep(0.3)

    sim = TemperatureSensorSimulator(SensorConfig(seed=1))
    sim.go_offline()
    publisher = SensorMqttPublisher(sim, publisher_connection, sensor_id="temp-sensor-offline")

    publisher.publish_reading()

    received = subscriber.wait_for_messages(count=1, timeout=5.0)
    assert received
    message = subscriber.received_messages[0]
    assert message.status.value == "OFFLINE"
    assert message.valid is False
    assert message.temperature is None


def test_publish_without_connection_returns_false():
    """Publishing on a never-connected client must fail explicitly, not silently."""
    conn = MqttConnection(client_id=_unique_client_id("test-unconnected"))
    result = conn.publish(settings.mqtt_topic_temperature, "{}")
    assert result is False


def test_malformed_payload_published_directly_is_flagged_invalid_by_subscriber(
    publisher_connection, subscriber_connection
):
    """
    Publishes a deliberately malformed payload straight through the raw
    connection (bypassing the publisher/message schema) to confirm the
    subscriber's validation layer correctly rejects it rather than
    crashing or silently accepting it.
    """
    subscriber = SensorMqttSubscriber(
        subscriber_connection, topics=[settings.mqtt_topic_temperature]
    )
    subscriber.subscribe_all()
    time.sleep(0.3)

    publisher_connection.publish(settings.mqtt_topic_temperature, "{not valid json")

    time.sleep(1.0)  # give the message time to arrive and be processed

    assert len(subscriber.received_messages) == 0
    assert len(subscriber.invalid_messages) == 1
    assert subscriber.invalid_messages[0].topic == settings.mqtt_topic_temperature
