"""
WHAT:
    The data models used by the IoT simulator: sensor status, sensor
    configuration, and individual sensor readings.

WHY:
    Everything downstream (MQTT payloads in Phase 3, fault injection in
    Phase 4, test execution in Phase 7) needs a single, well-typed
    definition of "what a sensor reading looks like." Defining these as
    Pydantic models now means every later module gets automatic
    validation and JSON serialization for free, and we avoid ad-hoc
    dicts with typos in key names scattered across the codebase.

HOW:
    - `SensorStatus`: an enum, ONLINE or OFFLINE.
    - `SensorConfig`: the tunable parameters of the simulator (range,
      accuracy, sampling interval, and the seed that makes it
      deterministic).
    - `SensorReading`: one immutable snapshot produced by a `tick()` —
      includes a virtual timestamp (not real wall-clock time, see
      simulator.py for why), the tick number, the value, and whether the
      simulator was online when it was produced.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SensorStatus(str, Enum):
    """Current operational status of the simulated sensor."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class SensorConfig(BaseModel):
    """
    Configuration for the temperature sensor simulator.

    Defaults match the example specification from the project brief:
    -40°C to 125°C, ±0.5°C accuracy, 1 second sampling interval.
    """

    device_name: str = Field(default="Temperature Sensor")
    min_temperature_c: float = Field(default=-40.0)
    max_temperature_c: float = Field(default=125.0)
    accuracy_c: float = Field(
        default=0.5, gt=0, description="± accuracy band applied as reading noise"
    )
    sampling_interval_seconds: float = Field(default=1.0, gt=0)

    # A fixed base temperature the sensor drifts gently around during
    # NORMAL operation, kept comfortably inside [min, max] by default.
    base_temperature_c: float = Field(default=25.0)

    # Seed for the internal deterministic random generator. Same seed +
    # same sequence of tick() calls ALWAYS produces the same readings —
    # this is what "deterministic" means here (see simulator.py).
    seed: int = Field(default=42)

    @field_validator("max_temperature_c")
    @classmethod
    def _max_above_min(cls, v: float, info) -> float:
        min_v = info.data.get("min_temperature_c")
        if min_v is not None and v <= min_v:
            raise ValueError("max_temperature_c must be greater than min_temperature_c")
        return v

    @field_validator("base_temperature_c")
    @classmethod
    def _base_within_range(cls, v: float, info) -> float:
        min_v = info.data.get("min_temperature_c")
        max_v = info.data.get("max_temperature_c")
        if min_v is not None and max_v is not None and not (min_v <= v <= max_v):
            raise ValueError(
                f"base_temperature_c ({v}) must be within "
                f"[{min_v}, {max_v}] for normal operation"
            )
        return v


class SensorReading(BaseModel):
    """One structured snapshot produced by the simulator on a tick."""

    tick: int = Field(ge=0)
    timestamp: datetime
    value_c: float
    unit: str = Field(default="C")
    status: SensorStatus
    valid: bool = Field(
        default=True,
        description=(
            "True if this reading is within the sensor's configured "
            "[min, max] range and the sensor was ONLINE when produced. "
            "Set False by out-of-range / fault scenarios (Phase 4)."
        ),
    )

    model_config = {"frozen": True}  # readings are immutable snapshots

    @staticmethod
    def offline_placeholder(tick: int, timestamp: datetime) -> "SensorReading":
        """A reading representing 'no data' because the sensor is OFFLINE."""
        return SensorReading(
            tick=tick,
            timestamp=timestamp,
            value_c=float("nan"),
            status=SensorStatus.OFFLINE,
            valid=False,
        )


def utc_epoch_start() -> datetime:
    """
    Fixed virtual clock origin (epoch) used by the simulator instead of
    real wall-clock time, so that reading timestamps are reproducible
    across runs. See simulator.py for how ticks are converted to time.
    """
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
