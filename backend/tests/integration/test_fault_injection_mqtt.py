"""
Phase 4 integration tests: faulted publisher/subscriber behavior over a
real, locally running Mosquitto broker. Gated (skipped, not faked) when no
broker is reachable, matching the Phase 3 integration convention. The
publisher/subscriber connection fixtures are reused from the Phase 3
integration module.

Each scenario drives a FaultInjectingPublisher (and, for reading faults, a
FaultInjectedSimulator) and verifies what the subscriber actually observes
over MQTT.
"""

import threading
import time

import pytest

from app.config import settings
from app.faults import FaultInjector, make_fault
from app.faults.models import FaultParams, FaultType, InjectionCondition
from app.faults.mqtt_interceptor import FaultInjectingPublisher
from app.faults.simulator_adapter import FaultInjectedSimulator
from app.iot.models import SensorConfig, SensorStatus
from app.iot.mqtt_subscriber import SensorMqttSubscriber
from app.iot.simulator import TemperatureSensorSimulator
from tests.integration.test_mqtt_communication import (
    BROKER_AVAILABLE,
    publisher_connection,
    subscriber_connection,
)

pytestmark = pytest.mark.skipif(
    not BROKER_AVAILABLE,
    reason=(
        f"No MQTT broker reachable at {settings.mqtt_broker_host}:"
        f"{settings.mqtt_broker_port} — start Mosquitto to run these tests "
        f"(see README 'Mosquitto setup')."
    ),
)


def _subscriber_and_publisher(
    subscriber_connection,
    publisher_connection,
    seed=7,
    sim_config=None,
    sensor_id="fault-sensor",
):
    subscriber = SensorMqttSubscriber(
        subscriber_connection, topics=[settings.mqtt_topic_temperature]
    )
    subscriber.subscribe_all()
    time.sleep(0.3)  # give the broker a moment to register the subscription

    injector = FaultInjector()
    sim = FaultInjectedSimulator(
        TemperatureSensorSimulator(sim_config or SensorConfig(seed=seed)), injector
    )
    publisher = FaultInjectingPublisher(
        sim, publisher_connection, injector, sensor_id=sensor_id
    )
    return subscriber, publisher, injector


def test_out_of_range_reading_arrives_with_fault_markers(
    publisher_connection, subscriber_connection
):
    config = SensorConfig(
        min_temperature_c=0.0, max_temperature_c=50.0, base_temperature_c=25.0, seed=3
    )
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection,
        publisher_connection,
        sim_config=config,
        sensor_id="fault-range",
    )
    injector.inject(
        make_fault(
            FaultType.SENSOR_OUT_OF_RANGE, params=FaultParams(overshoot_c=10.0)
        )
    )

    publisher.publish_reading()

    assert subscriber.wait_for_messages(count=1, timeout=5.0)
    message = subscriber.received_messages[0]
    assert message.temperature == 60.0  # max=50 + overshoot=10
    assert message.valid is False
    assert message.status is SensorStatus.ONLINE


def test_device_disconnect_publishes_offline_placeholder(
    publisher_connection, subscriber_connection
):
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection, publisher_connection, sensor_id="fault-offline"
    )
    injector.inject(make_fault(FaultType.DEVICE_DISCONNECT))

    publisher.publish_reading()

    assert subscriber.wait_for_messages(count=1, timeout=5.0)
    message = subscriber.received_messages[0]
    assert message.status is SensorStatus.OFFLINE
    assert message.valid is False
    assert message.temperature is None


def test_missing_message_reduces_received_count(
    publisher_connection, subscriber_connection
):
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection, publisher_connection, sensor_id="fault-missing"
    )
    injector.inject(
        make_fault(
            FaultType.MISSING_MESSAGE,
            injection_condition=InjectionCondition(start_tick=2, end_tick=3),
        )
    )

    published = publisher.publish_n_readings(4)

    assert subscriber.wait_for_messages(count=3, timeout=5.0)
    assert len(subscriber.received_messages) == 3
    assert len(subscriber.invalid_messages) == 0
    expected = {published[0].timestamp, published[1].timestamp, published[3].timestamp}
    assert {m.timestamp for m in subscriber.received_messages} == expected


def test_duplicate_message_received_twice(
    publisher_connection, subscriber_connection
):
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection, publisher_connection, sensor_id="fault-duplicate"
    )
    injector.inject(
        make_fault(
            FaultType.DUPLICATE_MESSAGE,
            params=FaultParams(duplicate_count=1),
            injection_condition=InjectionCondition(start_tick=1, end_tick=2),
        )
    )

    published = publisher.publish_n_readings(3)

    assert subscriber.wait_for_messages(count=4, timeout=5.0)
    assert len(subscriber.received_messages) == 4
    r0, r1, r2 = (r.timestamp for r in published)
    assert [m.timestamp for m in subscriber.received_messages] == [r0, r1, r1, r2]


def test_invalid_payload_flagged_by_subscriber(
    publisher_connection, subscriber_connection
):
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection, publisher_connection, sensor_id="fault-invalid"
    )
    injector.inject(
        make_fault(
            FaultType.INVALID_PAYLOAD,
            params=FaultParams(invalid_payload_kind="malformed_json"),
            injection_condition=InjectionCondition(start_tick=1, end_tick=2),
        )
    )

    publisher.publish_n_readings(3)

    assert subscriber.wait_for_messages(count=2, timeout=5.0)
    time.sleep(1.0)  # let the corrupt payload arrive and be processed
    assert len(subscriber.invalid_messages) == 1
    assert subscriber.invalid_messages[0].topic == settings.mqtt_topic_temperature


def test_mqtt_disconnect_blocks_until_window_ends(
    publisher_connection, subscriber_connection
):
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection, publisher_connection, sensor_id="fault-disconnect"
    )
    fault_id = injector.inject(
        make_fault(
            FaultType.MQTT_DISCONNECT,
            injection_condition=InjectionCondition(start_tick=0, end_tick=2),
        )
    )

    published = publisher.publish_n_readings(3)

    assert subscriber.wait_for_messages(count=1, timeout=5.0)
    assert len(subscriber.received_messages) == 1
    assert subscriber.received_messages[0].timestamp == published[2].timestamp
    assert injector.count_for(fault_id) == 2


def test_delayed_message_arrives_after_delay(
    publisher_connection, subscriber_connection
):
    subscriber, publisher, injector = _subscriber_and_publisher(
        subscriber_connection, publisher_connection, sensor_id="fault-delayed"
    )
    injector.inject(
        make_fault(
            FaultType.DELAYED_MESSAGE,
            params=FaultParams(delay_seconds=1.5),
            injection_condition=InjectionCondition(start_tick=0, end_tick=1),
        )
    )

    thread = threading.Thread(target=publisher.publish_reading)
    thread.start()

    time.sleep(0.3)  # well before the 1.5s delay elapses
    assert subscriber.wait_for_messages(count=1, timeout=0.2) is False

    thread.join(timeout=10.0)
    assert not thread.is_alive()
    assert subscriber.wait_for_messages(count=1, timeout=5.0)