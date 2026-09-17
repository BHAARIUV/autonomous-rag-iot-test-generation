"""
Phase 2 unit tests for the deterministic temperature sensor simulator.

Covers:
- Determinism (same seed -> identical reading sequence)
- Configurable min/max range
- Sampling interval affecting timestamps
- ONLINE/OFFLINE status behavior
- reset() reproducibility
"""

from datetime import timedelta

import pytest

from app.iot.models import SensorConfig, SensorStatus, utc_epoch_start
from app.iot.simulator import TemperatureSensorSimulator


def test_deterministic_sequence_same_seed():
    """Two simulators with the same seed must produce identical readings."""
    sim_a = TemperatureSensorSimulator(SensorConfig(seed=123))
    sim_b = TemperatureSensorSimulator(SensorConfig(seed=123))

    readings_a = [sim_a.tick() for _ in range(10)]
    readings_b = [sim_b.tick() for _ in range(10)]

    assert readings_a == readings_b


def test_different_seed_gives_different_sequence():
    """Sanity check: different seeds should (almost certainly) diverge."""
    sim_a = TemperatureSensorSimulator(SensorConfig(seed=1))
    sim_b = TemperatureSensorSimulator(SensorConfig(seed=2))

    readings_a = [sim_a.tick() for _ in range(10)]
    readings_b = [sim_b.tick() for _ in range(10)]

    assert readings_a != readings_b


def test_reset_reproduces_original_sequence():
    """reset() should let the same simulator instance replay identically."""
    sim = TemperatureSensorSimulator(SensorConfig(seed=7))

    first_pass = [sim.tick() for _ in range(5)]
    sim.reset()
    second_pass = [sim.tick() for _ in range(5)]

    assert first_pass == second_pass


def test_readings_stay_within_configured_range():
    """Normal operation must never leave [min_temperature_c, max_temperature_c]."""
    config = SensorConfig(min_temperature_c=-10.0, max_temperature_c=50.0, base_temperature_c=20.0)
    sim = TemperatureSensorSimulator(config)

    for _ in range(200):
        reading = sim.tick()
        assert config.min_temperature_c <= reading.value_c <= config.max_temperature_c
        assert reading.valid is True


def test_sampling_interval_drives_timestamps():
    """Consecutive readings must be spaced exactly sampling_interval_seconds apart."""
    config = SensorConfig(sampling_interval_seconds=2.5)
    sim = TemperatureSensorSimulator(config)

    r0 = sim.tick()
    r1 = sim.tick()
    r2 = sim.tick()

    assert r0.timestamp == utc_epoch_start()
    assert r1.timestamp - r0.timestamp == timedelta(seconds=2.5)
    assert r2.timestamp - r1.timestamp == timedelta(seconds=2.5)


def test_default_status_is_online():
    sim = TemperatureSensorSimulator()
    assert sim.status == SensorStatus.ONLINE
    reading = sim.tick()
    assert reading.status == SensorStatus.ONLINE
    assert reading.valid is True


def test_offline_produces_invalid_placeholder_reading():
    sim = TemperatureSensorSimulator()
    sim.go_offline()

    reading = sim.tick()

    assert sim.status == SensorStatus.OFFLINE
    assert reading.status == SensorStatus.OFFLINE
    assert reading.valid is False
    assert reading.value_c != reading.value_c  # NaN check (NaN != NaN)


def test_going_back_online_resumes_normal_readings():
    sim = TemperatureSensorSimulator()
    sim.go_offline()
    sim.tick()  # offline reading, tick 0
    sim.go_online()

    reading = sim.tick()  # tick 1, back online

    assert reading.status == SensorStatus.ONLINE
    assert reading.valid is True
    assert reading.tick == 1


def test_tick_count_increments_regardless_of_status():
    sim = TemperatureSensorSimulator()
    sim.tick()
    sim.go_offline()
    sim.tick()
    sim.go_online()
    sim.tick()

    assert sim.tick_count == 3


def test_config_rejects_max_not_greater_than_min():
    with pytest.raises(ValueError):
        SensorConfig(min_temperature_c=50.0, max_temperature_c=10.0)


def test_config_rejects_base_temperature_outside_range():
    with pytest.raises(ValueError):
        SensorConfig(min_temperature_c=0.0, max_temperature_c=10.0, base_temperature_c=100.0)


def test_custom_device_name_and_config_are_respected():
    config = SensorConfig(
        device_name="Freezer Sensor",
        min_temperature_c=-40.0,
        max_temperature_c=125.0,
        base_temperature_c=25.0,
        sampling_interval_seconds=1.0,
    )
    sim = TemperatureSensorSimulator(config)
    assert sim.config.device_name == "Freezer Sensor"
    reading = sim.tick()
    assert reading.unit == "C"
