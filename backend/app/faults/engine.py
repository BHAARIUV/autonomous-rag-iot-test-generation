"""
WHAT:
    The fault injection engine: registers fault definitions, tracks which
    are active, decides, purely from data, WHETHER and WHEN a fault fires,
    and maintains the full execution history of every firing.

WHY:
    Adapters (FaultInjectedSimulator / FaultInjectingPublisher) must make
    identical injection decisions every time the same scenario is run.
    Centralizing all decision logic here means every adapter shares a
    single code path for "which fault applies at this index?" and "record
    the hit", so the decisions and the history can never drift apart — a
    key part of the deterministic, reproducible behavior Phase 4 requires.

HOW:
    - add_fault(spec) registers a dormant FaultSpec; inject(spec) registers
      AND activates it immediately.
    - should_inject(fault_id, index) consults enabled flag, active state and
      the injection-condition window.
    - sensor_fault_at(index) / transport_fault_at(index) return the
      highest-precedence eligible fault for the simulator adapter and the
      MQTT interceptor respectively (or None).
    - record(...) appends a FaultRecord to the history.
    - reset() deactivates every fault and clears the history.

HOW TO VERIFY:
    See tests/unit/test_fault_engine.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from app.faults.models import (
    FaultImpact,
    FaultRecord,
    FaultSpec,
    FaultType,
    READING_FAULT_PRECEDENCE,
    TRANSPORT_FAULT_PRECEDENCE,
)


class FaultInjector:
    """Registry + decision engine for injected faults."""

    def __init__(self) -> None:
        self._specs: dict[str, FaultSpec] = {}
        self._active: set[str] = set()
        self._history: list[FaultRecord] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_fault(self, spec: FaultSpec) -> str:
        """Register a dormant fault. Returns the fault_id."""
        if spec.fault_id in self._specs:
            raise ValueError(f"fault_id '{spec.fault_id}' is already registered")
        self._specs[spec.fault_id] = spec
        logger.debug(f"Registered fault '{spec.fault_id}' ({spec.fault_type.value})")
        return spec.fault_id

    def inject(self, spec: FaultSpec) -> str:
        """Register AND activate a fault immediately. Returns the fault_id."""
        fault_id = self.add_fault(spec)
        self.activate(fault_id)
        return fault_id

    def remove_fault(self, fault_id: str) -> None:
        """Unregister a fault (also deactivates it if active)."""
        if fault_id not in self._specs:
            raise KeyError(f"No fault registered with fault_id '{fault_id}'")
        self._active.discard(fault_id)
        del self._specs[fault_id]
        logger.debug(f"Removed fault '{fault_id}'")

    def spec(self, fault_id: str) -> FaultSpec:
        """Return the registered FaultSpec, raising KeyError if unknown."""
        return self._spec(fault_id)

    def _spec(self, fault_id: str) -> FaultSpec:
        if fault_id not in self._specs:
            raise KeyError(f"No fault registered with fault_id '{fault_id}'")
        return self._specs[fault_id]

    # ------------------------------------------------------------------
    # Activation / enable-disable control
    # ------------------------------------------------------------------

    def activate(self, fault_id: str) -> None:
        """Arm an enabled fault so it can fire."""
        spec = self._spec(fault_id)
        if not spec.enabled:
            raise ValueError(f"Cannot activate disabled fault '{fault_id}'")
        self._active.add(fault_id)
        logger.info(f"Activated fault '{fault_id}' ({spec.fault_type.value})")

    def deactivate(self, fault_id: str) -> None:
        """Disarm a fault (it remains registered but stops firing)."""
        self._active.discard(fault_id)
        logger.info(f"Deactivated fault '{fault_id}'")

    def set_enabled(self, fault_id: str, enabled: bool) -> None:
        """Enable or disable a fault. Disabling also deactivates it."""
        self._spec(fault_id)
        self._specs[fault_id] = self._specs[fault_id].model_copy(
            update={"enabled": enabled}
        )
        if not enabled:
            self._active.discard(fault_id)

    def is_active(self, fault_id: str) -> bool:
        spec = self._specs.get(fault_id)
        return bool(spec and spec.enabled and fault_id in self._active)

    def active_faults(self, impact: FaultImpact | None = None) -> list[FaultSpec]:
        """Active fault specs, in registration order, optionally filtered by impact."""
        specs = [s for fid, s in self._specs.items() if fid in self._active]
        if impact is not None:
            specs = [s for s in specs if s.expected_detection.impacted_subsystem is impact]
        return specs

    # ------------------------------------------------------------------
    # Decision-making
    # ------------------------------------------------------------------

    def should_inject(self, fault_id: str, index: int) -> bool:
        """True if a registered, enabled, active fault fires at `index`."""
        spec = self._specs.get(fault_id)
        if spec is None:
            return False
        if not spec.enabled or fault_id not in self._active:
            return False
        return spec.injection_condition.applies_at(index)

    def sensor_fault_at(self, index: int) -> FaultSpec | None:
        """
        The highest-precedence active READING-impact fault eligible at the
        given sensor tick index, or None. Used by FaultInjectedSimulator.
        """
        eligible = [
            spec
            for spec in self.active_faults()
            if spec.expected_detection.impacted_subsystem is FaultImpact.READING
            and spec.injection_condition.applies_at(index)
        ]
        if not eligible:
            return None

        def _key(spec: FaultSpec):
            return (READING_FAULT_PRECEDENCE.get(spec.fault_type, 99), spec.fault_id)

        return min(eligible, key=_key)

    def transport_fault_at(self, index: int) -> FaultSpec | None:
        """
        The highest-precedence active MESSAGE/CONNECTION-impact fault
        eligible at the given publisher message index, or None. Used by
        FaultInjectingPublisher.
        """
        eligible = [
            spec
            for spec in self.active_faults()
            if spec.expected_detection.impacted_subsystem
            in (FaultImpact.MESSAGE, FaultImpact.CONNECTION)
            and spec.injection_condition.applies_at(index)
        ]
        if not eligible:
            return None

        def _key(spec: FaultSpec):
            return (TRANSPORT_FAULT_PRECEDENCE.get(spec.fault_type, 99), spec.fault_id)

        return min(eligible, key=_key)

    # ------------------------------------------------------------------
    # Execution history
    # ------------------------------------------------------------------

    def record(
        self,
        fault_id: str,
        index: int,
        detail: str = "",
        timestamp: datetime | None = None,
    ) -> FaultRecord:
        """Record one firing of a registered fault into the history."""
        spec = self._spec(fault_id)
        record = FaultRecord(
            fault_id=fault_id,
            fault_type=spec.fault_type,
            severity=spec.severity,
            tick_index=index,
            timestamp=timestamp or datetime.now(timezone.utc),
            detail=detail,
        )
        self._history.append(record)
        logger.debug(
            f"[fault] {spec.fault_type.value} '{fault_id}' @ index {index}: {detail}"
        )
        return record

    def count_for(self, fault_id: str) -> int:
        """Number of recorded firings for a fault."""
        return sum(1 for r in self._history if r.fault_id == fault_id)

    @property
    def history(self) -> list[FaultRecord]:
        """Copy of the execution history (never mutate the internal list)."""
        return list(self._history)

    def reset(self) -> None:
        """Deactivate every fault and clear the execution history."""
        self._active.clear()
        self._history.clear()
        logger.warning("FaultInjector reset: all faults deactivated, history cleared")