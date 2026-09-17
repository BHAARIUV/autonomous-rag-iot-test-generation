"""
WHAT:
    FaultInjectedSimulator — a drop-in wrapper around the Phase 2
    TemperatureSensorSimulator that intercepts tick() so READING-impact
    faults (SENSOR_OUT_OF_RANGE, SENSOR_UNDER_RANGE, INVALID_SENSOR_DATA,
    DEVICE_DISCONNECT) can be applied deterministically.

WHY:
    Phase 2's simulator is deliberately MQTT/fault-agnostic and must not
    be modified. Wrapping it keeps a single code path "simulator -> fault
    adapter -> publisher", which lets Phase 7's test execution reuse the
    exact same (unmodified) publisher code as the non-faulted path — the
    wrapper is interface-compatible with TemperatureSensorSimulator (tick,
    tick_count, status, go_online, go_offline, reset, config).

HOW:
    tick():
      1. Capture the current tick index (before advancing).
      2. Delegate to the wrapped simulator to advance its state.
      3. Ask the FaultInjector for the highest-precedence eligible
         READING fault at that index.
      4. If none applies, return the simulator's reading unchanged.
      5. Otherwise build a faulted SensorReading that replaces it,
         record the firing in the injector's history, and return it.
    The wrapped simulator's tick counter and RNG always advance, so the
    sequence stays deterministic and in sync whether or not a fault fires.

HOW TO VERIFY:
    See tests/unit/test_simulator_adapter.py and
    tests/integration/test_fault_injection_mqtt.py.
"""

from __future__ import annotations

from loguru import logger

from app.faults.engine import FaultInjector
from app.faults.models import FaultSpec, FaultType
from app.iot.models import SensorConfig, SensorReading, SensorStatus
from app.iot.simulator import TemperatureSensorSimulator


def _faulted_reading(
    spec: FaultSpec, config: SensorConfig, reading: SensorReading
) -> tuple[SensorReading, str]:
    """
    Build the faulted SensorReading for an eligible READING fault plus a
    human-readable detail string for the execution history.
    """
    params = spec.params
    base = dict(tick=reading.tick, timestamp=reading.timestamp)

    if spec.fault_type == FaultType.SENSOR_OUT_OF_RANGE:
        value_c = config.max_temperature_c + params.overshoot_c
        detail = f"value_c={value_c:.3f} exceeds max={config.max_temperature_c}"
        return (
            SensorReading(
                **base, value_c=value_c, status=SensorStatus.ONLINE, valid=False
            ),
            detail,
        )

    if spec.fault_type == FaultType.SENSOR_UNDER_RANGE:
        value_c = config.min_temperature_c - params.undershoot_c
        detail = f"value_c={value_c:.3f} below min={config.min_temperature_c}"
        return (
            SensorReading(
                **base, value_c=value_c, status=SensorStatus.ONLINE, valid=False
            ),
            detail,
        )

    if spec.fault_type == FaultType.INVALID_SENSOR_DATA:
        value_c = float("nan") if params.invalid_data_kind == "nan" else float("inf")
        detail = f"value_c={params.invalid_data_kind} (non-numeric) while ONLINE"
        return (
            SensorReading(
                **base, value_c=value_c, status=SensorStatus.ONLINE, valid=False
            ),
            detail,
        )

    if spec.fault_type == FaultType.DEVICE_DISCONNECT:
        detail = "device disconnected; reading reported OFFLINE"
        return (
            SensorReading(
                **base,
                value_c=float("nan"),
                status=SensorStatus.OFFLINE,
                valid=False,
            ),
            detail,
        )

    raise ValueError(f"not a reading fault: {spec.fault_type}")


class FaultInjectedSimulator:
    """
    Interface-compatible wrapper around TemperatureSensorSimulator that
    applies READING-impact faults via a shared FaultInjector.
    """

    def __init__(
        self, simulator: TemperatureSensorSimulator, injector: FaultInjector
    ) -> None:
        self._simulator = simulator
        self._injector = injector

    # ------------------------------------------------------------------
    # Delegated simulator surface (unmodified behavior)
    # ------------------------------------------------------------------

    @property
    def config(self) -> SensorConfig:
        return self._simulator.config

    @property
    def status(self) -> SensorStatus:
        return self._simulator.status

    @property
    def tick_count(self) -> int:
        return self._simulator.tick_count

    @property
    def injector(self) -> FaultInjector:
        return self._injector

    def go_online(self) -> None:
        self._simulator.go_online()

    def go_offline(self) -> None:
        self._simulator.go_offline()

    def reset(self) -> None:
        self._simulator.reset()

    # ------------------------------------------------------------------
    # Intercepted core
    # ------------------------------------------------------------------

    def tick(self) -> SensorReading:
        tick_index = self._simulator.tick_count
        reading = self._simulator.tick()

        spec = self._injector.sensor_fault_at(tick_index)
        if spec is None:
            return reading

        faulted, detail = _faulted_reading(spec, self._simulator.config, reading)
        self._injector.record(
            spec.fault_id, tick_index, detail=detail, timestamp=reading.timestamp
        )
        logger.debug(
            f"[fault-injected-simulator] tick {tick_index}: "
            f"{spec.fault_type.value} -> {faulted.value_c}C valid={faulted.valid}"
        )
        return faulted