"""
WHAT:
    A thin wrapper around `paho-mqtt`'s Client that handles connecting to
    the broker, automatic reconnection with a bounded retry count,
    graceful disconnect, and consistent logging/error handling. Both the
    publisher and subscriber (below) are built on top of this one class
    instead of talking to paho-mqtt directly.

WHY:
    paho-mqtt's raw API requires correctly wiring up several callbacks
    (`on_connect`, `on_disconnect`, `on_message`, ...), managing its
    background network loop thread, and handling transient connection
    failures yourself. Centralizing that here means:
      - The publisher and subscriber modules stay focused on their own
        job (publishing sensor readings / receiving and validating
        messages) instead of duplicating connection-handling code.
      - Reconnection behavior (attempts, delay) is configured once via
        Settings/.env and applied consistently everywhere.
      - Every connection event is logged in one place.

HOW:
    Uses paho-mqtt's CallbackAPIVersion.VERSION2 (the current recommended
    API as of paho-mqtt 2.x). `connect()` starts the client's background
    network loop (`loop_start()`) and blocks (with a timeout) until the
    `on_connect` callback confirms the broker accepted the connection.
    If the broker is unreachable, `connect()` raises `MqttConnectionError`
    rather than silently returning — callers (and tests) must be able to
    tell "definitely connected" from "who knows."

HOW TO VERIFY:
    Requires a running local Mosquitto broker (see README "Mosquitto
    setup"). See tests/integration/test_mqtt_communication.py, which is
    skipped automatically if no broker is reachable on the configured
    host/port.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt
from loguru import logger

from app.config import settings


class MqttConnectionError(Exception):
    """Raised when the MQTT client fails to connect to the broker."""


class MqttConnection:
    """
    Manages a single MQTT client connection: connect, reconnect,
    graceful disconnect, and dispatching incoming messages to a
    caller-supplied handler.
    """

    def __init__(
        self,
        client_id: str | None = None,
        host: str | None = None,
        port: int | None = None,
        on_message: Callable[[str, bytes], None] | None = None,
    ) -> None:
        self.host = host or settings.mqtt_broker_host
        self.port = port or settings.mqtt_broker_port
        self.client_id = client_id or settings.mqtt_client_id
        self._external_on_message = on_message

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
        )
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._client.on_message = self._handle_message

        self._connected_event = threading.Event()
        self._connect_rc: int | None = None
        self._is_connected = False
        self._unexpected_disconnect = False

    # ------------------------------------------------------------------
    # Callbacks (paho-mqtt VERSION2 signatures)
    # ------------------------------------------------------------------

    def _handle_connect(self, client, userdata, connect_flags, reason_code, properties):
        if reason_code == 0:
            self._is_connected = True
            self._connect_rc = 0
            logger.info(
                f"MQTT client '{self.client_id}' connected to {self.host}:{self.port}"
            )
        else:
            self._connect_rc = int(reason_code)
            logger.error(
                f"MQTT client '{self.client_id}' failed to connect: reason_code={reason_code}"
            )
        self._connected_event.set()

    def _handle_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._is_connected = False
        if reason_code != 0:
            self._unexpected_disconnect = True
            logger.warning(
                f"MQTT client '{self.client_id}' disconnected unexpectedly: "
                f"reason_code={reason_code}"
            )
        else:
            logger.info(f"MQTT client '{self.client_id}' disconnected cleanly")

    def _handle_message(self, client, userdata, message: mqtt.MQTTMessage):
        logger.debug(
            f"MQTT client '{self.client_id}' received message on '{message.topic}' "
            f"({len(message.payload)} bytes)"
        )
        if self._external_on_message is not None:
            try:
                self._external_on_message(message.topic, message.payload)
            except Exception as exc:  # never let a bad handler kill the network loop
                logger.error(f"Error in on_message handler for '{message.topic}': {exc}")

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self) -> None:
        """
        Connect to the broker and block until either the connection is
        confirmed or the configured timeout elapses.

        Raises:
            MqttConnectionError: on timeout, refusal, or any socket-level
            failure (e.g. broker not running).
        """
        self._connected_event.clear()
        logger.info(
            f"MQTT client '{self.client_id}' connecting to {self.host}:{self.port}..."
        )
        try:
            self._client.connect(
                self.host, self.port, keepalive=settings.mqtt_keepalive_seconds
            )
        except (OSError, ConnectionRefusedError) as exc:
            raise MqttConnectionError(
                f"Could not reach MQTT broker at {self.host}:{self.port}: {exc}"
            ) from exc

        self._client.loop_start()

        confirmed = self._connected_event.wait(timeout=settings.mqtt_connect_timeout_seconds)
        if not confirmed:
            self._client.loop_stop()
            raise MqttConnectionError(
                f"Timed out waiting for MQTT broker {self.host}:{self.port} to accept connection"
            )
        if self._connect_rc != 0:
            self._client.loop_stop()
            raise MqttConnectionError(
                f"MQTT broker rejected connection: reason_code={self._connect_rc}"
            )

    def connect_with_retry(self, max_attempts: int | None = None) -> None:
        """
        Attempt to connect, retrying with the configured delay on
        failure, up to `max_attempts` (defaults to
        settings.mqtt_max_reconnect_attempts).

        Raises:
            MqttConnectionError: if every attempt fails.
        """
        attempts = max_attempts or settings.mqtt_max_reconnect_attempts
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                self.connect()
                return
            except MqttConnectionError as exc:
                last_error = exc
                logger.warning(
                    f"MQTT connect attempt {attempt}/{attempts} failed: {exc}"
                )
                if attempt < attempts:
                    time.sleep(settings.mqtt_reconnect_delay_seconds)

        raise MqttConnectionError(
            f"Failed to connect to MQTT broker after {attempts} attempts"
        ) from last_error

    def disconnect(self) -> None:
        """Gracefully disconnect and stop the background network loop."""
        logger.info(f"MQTT client '{self.client_id}' disconnecting...")
        self._client.disconnect()
        self._client.loop_stop()
        self._is_connected = False

    # ------------------------------------------------------------------
    # Publish / subscribe primitives
    # ------------------------------------------------------------------

    def publish(self, topic: str, payload: str, qos: int | None = None) -> bool:
        """
        Publish a message. Returns True if the broker accepted the
        publish call (does not guarantee QoS-1/2 delivery confirmation —
        that would require tracking on_publish per message id, which
        callers needing guaranteed delivery should extend this with).
        """
        if not self._is_connected:
            logger.error(
                f"Cannot publish to '{topic}': MQTT client '{self.client_id}' is not connected"
            )
            return False

        result = self._client.publish(topic, payload, qos=qos if qos is not None else settings.mqtt_qos)
        success = result.rc == mqtt.MQTT_ERR_SUCCESS
        if not success:
            logger.error(f"Publish to '{topic}' failed: rc={result.rc}")
        else:
            logger.debug(f"Published to '{topic}': {len(payload)} bytes")
        return success

    def subscribe(self, topic: str, qos: int | None = None) -> None:
        if not self._is_connected:
            raise MqttConnectionError(
                f"Cannot subscribe to '{topic}': client is not connected"
            )
        self._client.subscribe(topic, qos=qos if qos is not None else settings.mqtt_qos)
        logger.info(f"MQTT client '{self.client_id}' subscribed to '{topic}'")
