"""
WHAT:
    FaultInjectingPublisher — mirrors the SensorMqttPublisher public
    interface (publish_reading, publish_n_readings) but routes every
    message through the FaultInjector so MESSAGE / CONNECTION-impact
    faults (MISSING_MESSAGE, DELAYED_MESSAGE, DUPLICATE_MESSAGE,
    MQTT_DISCONNECT, MQTT_TIMEOUT, INVALID_PAYLOAD) can be applied at the
    transport boundary.

WHY:
    Phase 3's publisher must not be modified or corrupted. This interceptor
    sits ABOVE it in the call stack and composes the exact same building
    blocks (simulator.tick, reading_to_mqtt_message, serialize_message,
    connection.publish, configured topics). Because it is interface-
    compatible with SensorMqttPublisher, later phases can swap a faulted
    publisher in without touching the subscriber or test harness.

HOW:
    publish_reading():
      1. Tick the simulator (which may itself be a FaultInjectedSimulator).
      2. Serialize the reading into the standard MQTT payload.
      3. Ask the injector for the highest-precedence eligible transport
         fault at the current message index.
      4. No fault: publish temperature + status exactly like the standard
         publisher (byte-identical behavior — verified by a parity test).
      5. Fault: apply the type-specific effect, e.g. suppress (MISSING /
         MQTT_DISCONNECT / MQTT_TIMEOUT), sleep then send (DELAYED),
         publish N+1 copies (DUPLICATE), or publish a corrupted payload
         (INVALID_PAYLOAD). Every firing is recorded in the history.
    Index semantics: transport faults are keyed on the publisher's own
    message counter, which is independent of the simulator's tick counter.

HOW TO VERIFY:
    See tests/unit/test_mqtt_interceptor.py and
    tests/integration/test_fault_injection_mqtt.py.
"""

from __future__ import annotations

import json
import time

from loguru import logger

from app.config import settings
from app.faults.engine import FaultInjector
from app.faults.models import FaultSpec, FaultType
from app.iot.mqtt_messages import SensorMqttMessage, reading_to_mqtt_message, serialize_message
from app.iot.simulator import TemperatureSensorSimulator


class FaultInjectingPublisher:
    """
    Interceptor for the MQTT publish path. Interface-compatible with
    SensorMqttPublisher so it can be used as a drop-in replacement.
    """

    def __init__(
        self,
        simulator: TemperatureSensorSimulator,
        connection,
        injector: FaultInjector,
        sensor_id: str | None = None,
    ) -> None:
        self.simulator = simulator
        self.connection = connection
        self.injector = injector
        self.sensor_id = sensor_id or simulator.config.device_name
        self._message_index = 0

    # ------------------------------------------------------------------
    # Public interface (mirrors SensorMqttPublisher)
    # ------------------------------------------------------------------

    @property
    def message_index(self) -> int:
        """Number of publish requests handled by this publisher so far."""
        return self._message_index

    def reset(self) -> None:
        """Reset the publisher's message counter to 0."""
        self._message_index = 0

    def publish_reading(self):
        """
        Tick the simulator and publish the result (through the injector's
        transport fault gate). Returns the raw SensorReading, matching
        SensorMqttPublisher.publish_reading() semantics.
        """
        reading = self.simulator.tick()
        message = reading_to_mqtt_message(self.sensor_id, reading)
        payload = serialize_message(message)

        index = self._message_index
        self._message_index += 1

        fault = self.injector.transport_fault_at(index)
        if fault is None:
            self.connection.publish(settings.mqtt_topic_temperature, payload)
            self._publish_status(message)
            return reading

        self._apply_transport_fault(fault, index, message, payload)
        return reading

    def publish_n_readings(self, count: int) -> list:
        """Convenience helper: publish `count` consecutive readings."""
        readings = []
        for _ in range(count):
            readings.append(self.publish_reading())
        logger.info(f"Published {count} readings for sensor '{self.sensor_id}'")
        return readings

    # ------------------------------------------------------------------
    # Status topic helper (mirrors SensorMqttPublisher._publish_status)
    # ------------------------------------------------------------------

    def _publish_status(self, message: SensorMqttMessage) -> None:
        self.connection.publish(settings.mqtt_topic_status, serialize_message(message))

    # ------------------------------------------------------------------
    # Transport fault application
    # ------------------------------------------------------------------

    def _apply_transport_fault(
        self,
        fault: FaultSpec,
        index: int,
        message: SensorMqttMessage,
        payload: str,
    ) -> None:
        fault_type = fault.fault_type

        if fault_type == FaultType.MISSING_MESSAGE:
            self._record(
                fault,
                index,
                detail="reading suppressed; no messages published for this tick",
            )
            return

        if fault_type == FaultType.DELAYED_MESSAGE:
            delay = fault.params.delay_seconds
            detail = f"message held for {delay:.3f}s before publishing"
            time.sleep(delay)
            self.connection.publish(settings.mqtt_topic_temperature, payload)
            self._publish_status(message)
            self._record(fault, index, detail=detail)
            return

        if fault_type == FaultType.DUPLICATE_MESSAGE:
            copies = fault.params.duplicate_count + 1
            for _ in range(copies):
                self.connection.publish(settings.mqtt_topic_temperature, payload)
            self._publish_status(message)
            self._record(fault, index, detail=f"published message {copies} times")
            return

        if fault_type == FaultType.MQTT_DISCONNECT:
            self._record(fault, index, detail="publish suppressed: connection lost")
            return

        if fault_type == FaultType.MQTT_TIMEOUT:
            self._record(fault, index, detail="publish suppressed: broker unresponsive (timeout)")
            return

        if fault_type == FaultType.INVALID_PAYLOAD:
            bad_payload = self._corrupt_payload(
                fault.params.invalid_payload_kind, message
            )
            self.connection.publish(settings.mqtt_topic_temperature, bad_payload)
            self._publish_status(message)
            self._record(
                fault,
                index,
                detail=(
                    f"published corrupted payload "
                    f"(kind={fault.params.invalid_payload_kind})"
                ),
            )
            return

        raise ValueError(f"unhandled transport fault: {fault_type}")

    def _corrupt_payload(
        self, kind: str, message: SensorMqttMessage
    ) -> str | bytes:
        """Produce a deliberately corrupted payload of the requested kind."""
        if kind == "not_json":
            return b"\x7fCORRUPTED\xff\xfe\x00"
        if kind == "wrong_schema":
            return json.dumps({"unexpected_field": "not-a-sensor-message"})
        return "{ \"sensor_id\": \"broken\", "  # malformed JSON (default)

    def _record(self, fault: FaultSpec, index: int, detail: str) -> None:
        self.injector.record(fault.fault_id, index, detail=detail)