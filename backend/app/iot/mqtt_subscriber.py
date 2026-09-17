"""
WHAT:
    `SensorMqttSubscriber` subscribes to the sensor topics and collects
    validated `SensorMqttMessage` objects as they arrive, while tracking
    any messages that fail validation separately. This is what a test
    client (Phase 7's automated test execution) or a future dashboard
    would use to receive and check what the sensor actually published.

WHY:
    The project brief requires "The subscriber/test client should be
    able to receive and validate those readings." Validation must happen
    at the point of receipt — a subscriber that stores raw, unchecked
    payloads would let a malformed or malicious message flow silently
    into later analysis. This class guarantees every stored message has
    already passed `deserialize_message()`'s validation.

HOW:
    Wraps an `MqttConnection`, giving it an internal `_on_raw_message`
    callback. On each incoming message: try to deserialize + validate
    it; on success, append to `received_messages`; on failure, append
    the raw payload + error to `invalid_messages` (never silently
    dropped) and log a warning.

HOW TO VERIFY:
    See tests/integration/test_mqtt_communication.py.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from loguru import logger

from app.config import settings
from app.iot.mqtt_client import MqttConnection
from app.iot.mqtt_messages import MessageValidationError, SensorMqttMessage, deserialize_message


@dataclass
class InvalidMessageRecord:
    """A message that arrived on a subscribed topic but failed validation."""

    topic: str
    raw_payload: bytes
    error: str


class SensorMqttSubscriber:
    """Subscribes to sensor MQTT topics and validates incoming messages."""

    def __init__(self, connection: MqttConnection, topics: list[str] | None = None) -> None:
        self.connection = connection
        self.topics = topics or [
            settings.mqtt_topic_temperature,
            settings.mqtt_topic_status,
        ]
        self.received_messages: list[SensorMqttMessage] = []
        self.invalid_messages: list[InvalidMessageRecord] = []
        self._lock = threading.Lock()

        # Wire this subscriber's handler into the connection. Note: a
        # single MqttConnection can only have one on_message handler in
        # this simple design, so each subscriber should generally use
        # its own MqttConnection instance.
        connection._external_on_message = self._on_raw_message

    def subscribe_all(self) -> None:
        for topic in self.topics:
            self.connection.subscribe(topic)

    def _on_raw_message(self, topic: str, payload: bytes) -> None:
        try:
            message = deserialize_message(payload)
        except MessageValidationError as exc:
            logger.warning(f"Rejected invalid message on '{topic}': {exc}")
            with self._lock:
                self.invalid_messages.append(
                    InvalidMessageRecord(topic=topic, raw_payload=payload, error=str(exc))
                )
            return

        with self._lock:
            self.received_messages.append(message)
        logger.debug(
            f"Validated message received on '{topic}' from sensor '{message.sensor_id}'"
        )

    def wait_for_messages(self, count: int, timeout: float = 5.0) -> bool:
        """
        Block until at least `count` valid messages have been received,
        or `timeout` seconds elapse. Returns True if the count was
        reached, False on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.received_messages) >= count:
                    return True
            time.sleep(0.05)
        with self._lock:
            return len(self.received_messages) >= count

    def clear(self) -> None:
        with self._lock:
            self.received_messages.clear()
            self.invalid_messages.clear()
