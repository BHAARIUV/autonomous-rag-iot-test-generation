"""
WHAT:
    `SensorMqttPublisher` connects a Phase-2 `TemperatureSensorSimulator`
    to MQTT: each call to `publish_reading()` ticks the simulator once
    and publishes the resulting reading as a structured JSON message on
    `iot/sensor/temperature`, plus a lightweight status update on
    `iot/sensor/status`.

WHY:
    Keeping the simulator (Phase 2) MQTT-agnostic and putting all
    MQTT-specific logic in this wrapper means the simulator's core
    behavior didn't need to change at all for Phase 3 — exactly as
    required. This class is the only thing that knows both "how to tick
    a sensor" and "how to publish over MQTT."

HOW:
    Wraps a `TemperatureSensorSimulator` (Phase 2) and an
    `MqttConnection` (this phase). Converts each `SensorReading` into a
    `SensorMqttMessage` (via `reading_to_mqtt_message`), serializes it,
    and publishes it. The sensor_id used in messages defaults to the
    simulator's configured device_name.

HOW TO VERIFY:
    See tests/integration/test_mqtt_communication.py — publishes real
    readings against a local Mosquitto broker and confirms a subscriber
    receives and validates them.
"""

from __future__ import annotations

from loguru import logger

from app.config import settings
from app.iot.models import SensorReading
from app.iot.mqtt_client import MqttConnection
from app.iot.mqtt_messages import reading_to_mqtt_message, serialize_message
from app.iot.simulator import TemperatureSensorSimulator


class SensorMqttPublisher:
    """Publishes a simulated temperature sensor's readings over MQTT."""

    def __init__(
        self,
        simulator: TemperatureSensorSimulator,
        connection: MqttConnection,
        sensor_id: str | None = None,
    ) -> None:
        self.simulator = simulator
        self.connection = connection
        self.sensor_id = sensor_id or simulator.config.device_name

    def publish_reading(self) -> SensorReading:
        """
        Tick the simulator once, publish the resulting reading on the
        temperature topic, and publish a status update. Returns the raw
        SensorReading for callers/tests that want to inspect it directly.
        """
        reading = self.simulator.tick()
        message = reading_to_mqtt_message(self.sensor_id, reading)
        payload = serialize_message(message)

        self.connection.publish(settings.mqtt_topic_temperature, payload)
        self._publish_status(reading)

        return reading

    def _publish_status(self, reading: SensorReading) -> None:
        """Publish a minimal status update reusing the same message schema."""
        message = reading_to_mqtt_message(self.sensor_id, reading)
        payload = serialize_message(message)
        self.connection.publish(settings.mqtt_topic_status, payload)

    def publish_n_readings(self, count: int) -> list[SensorReading]:
        """Convenience helper: publish `count` consecutive readings."""
        readings = []
        for _ in range(count):
            readings.append(self.publish_reading())
        logger.info(f"Published {count} readings for sensor '{self.sensor_id}'")
        return readings
