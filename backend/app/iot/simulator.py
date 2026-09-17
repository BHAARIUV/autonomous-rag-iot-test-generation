"""
WHAT:
    A deterministic, in-memory simulator of a single temperature sensor.
    Each call to `tick()` advances an internal virtual clock by one
    sampling interval and returns a structured `SensorReading`.

WHY:
    Phase 0/1 established that the simulator must be deterministic so
    that automated tests can reliably reproduce conditions (rule from
    the master prompt: "The simulator must be deterministic enough that
    automated tests can reliably reproduce conditions"). Real sensors
    (and `random.random()` without a seed) are not reproducible — the
    same test run twice could give different pass/fail results, which
    would make coverage and fault-detection metrics meaningless.

    This module deliberately does NOT know about MQTT (Phase 3) or fault
    injection (Phase 4). It only knows how to produce believable
    NORMAL-operation temperature readings and track ONLINE/OFFLINE
    status. Keeping it self-contained means:
      - Phase 3 can wrap it and publish its readings over MQTT.
      - Phase 4 can call into it (or manipulate its config/state) to
        inject abnormal conditions, without touching this file.

HOW DETERMINISM WORKS:
    - The simulator uses `random.Random(seed)` — a *seeded* generator,
      not the global `random` module. Two simulators built with the same
      `SensorConfig.seed` and driven by the same number of `tick()`
      calls will ALWAYS produce byte-for-byte identical reading
      sequences.
    - Time is virtual, not `datetime.now()`. Tick 0 is at a fixed epoch
      (see `models.utc_epoch_start`), and tick N's timestamp is
      `epoch + N * sampling_interval_seconds`. This means timestamps are
      also perfectly reproducible.
    - Temperature values follow a smooth, gentle drift (a sine wave)
      around `base_temperature_c` plus small seeded "measurement noise"
      bounded by `accuracy_c`, then clipped to stay within
      [min_temperature_c, max_temperature_c] during NORMAL operation.
      (Going outside that range on purpose is a fault-injection concern,
      Phase 4 — this simulator's normal mode never produces it.)

HOW TO RUN (interactive check):
    python -c "
    from app.iot.simulator import TemperatureSensorSimulator
    sim = TemperatureSensorSimulator()
    for _ in range(3):
        print(sim.tick())
    "

HOW TO VERIFY:
    See tests/unit/test_simulator.py — covers determinism, range
    configuration, sampling interval timestamps, and ONLINE/OFFLINE
    status transitions.
"""

from __future__ import annotations

import math
import random
from datetime import timedelta

from loguru import logger

from app.iot.models import SensorConfig, SensorReading, SensorStatus, utc_epoch_start


class TemperatureSensorSimulator:
    """A deterministic, standalone simulated temperature sensor."""

    def __init__(self, config: SensorConfig | None = None) -> None:
        self.config = config or SensorConfig()
        self._status = SensorStatus.ONLINE
        self._tick_count = 0
        self._rng = random.Random(self.config.seed)
        logger.debug(
            f"Simulator initialized: device='{self.config.device_name}', "
            f"range=[{self.config.min_temperature_c}, {self.config.max_temperature_c}]C, "
            f"seed={self.config.seed}"
        )

    # ------------------------------------------------------------------
    # Status control
    # ------------------------------------------------------------------

    @property
    def status(self) -> SensorStatus:
        return self._status

    def go_online(self) -> None:
        """Bring the sensor ONLINE. Ticking will resume producing real values."""
        if self._status != SensorStatus.ONLINE:
            logger.info(f"Sensor '{self.config.device_name}' going ONLINE")
        self._status = SensorStatus.ONLINE

    def go_offline(self) -> None:
        """Take the sensor OFFLINE. Ticking will produce offline placeholders."""
        if self._status != SensorStatus.OFFLINE:
            logger.info(f"Sensor '{self.config.device_name}' going OFFLINE")
        self._status = SensorStatus.OFFLINE

    # ------------------------------------------------------------------
    # Core simulation
    # ------------------------------------------------------------------

    def tick(self) -> SensorReading:
        """
        Advance the simulator by one sampling interval and return the
        resulting SensorReading. If OFFLINE, returns an invalid
        placeholder reading (no real value) instead.
        """
        timestamp = utc_epoch_start() + timedelta(
            seconds=self._tick_count * self.config.sampling_interval_seconds
        )

        if self._status == SensorStatus.OFFLINE:
            reading = SensorReading.offline_placeholder(self._tick_count, timestamp)
            logger.debug(f"tick {self._tick_count}: OFFLINE, no data")
            self._tick_count += 1
            return reading

        value = self._generate_normal_value(self._tick_count)
        in_range = self.config.min_temperature_c <= value <= self.config.max_temperature_c

        reading = SensorReading(
            tick=self._tick_count,
            timestamp=timestamp,
            value_c=round(value, 3),
            status=self._status,
            valid=in_range,
        )
        logger.debug(f"tick {self._tick_count}: {reading.value_c}C (valid={reading.valid})")
        self._tick_count += 1
        return reading

    def _generate_normal_value(self, tick: int) -> float:
        """
        Deterministically compute a believable NORMAL-operation reading:
        a gentle sine-wave drift around base_temperature_c (amplitude is
        1/4 of the configured range, capped so it can't approach the
        min/max bounds) plus small seeded noise within accuracy_c, then
        clipped to the configured [min, max] as a safety net.
        """
        span = self.config.max_temperature_c - self.config.min_temperature_c
        amplitude = min(span * 0.05, 5.0)  # gentle drift, not a wild swing
        drift = amplitude * math.sin(tick / 20.0)
        noise = self._rng.uniform(-self.config.accuracy_c, self.config.accuracy_c)
        value = self.config.base_temperature_c + drift + noise
        return max(self.config.min_temperature_c, min(self.config.max_temperature_c, value))

    # ------------------------------------------------------------------
    # Test / reproducibility helpers
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """
        Reset the simulator back to tick 0 with a fresh seeded RNG
        (same seed as configured), so the exact same reading sequence
        can be reproduced again. Status is reset to ONLINE.
        """
        self._tick_count = 0
        self._rng = random.Random(self.config.seed)
        self._status = SensorStatus.ONLINE
        logger.debug(f"Simulator '{self.config.device_name}' reset to tick 0")

    @property
    def tick_count(self) -> int:
        return self._tick_count
