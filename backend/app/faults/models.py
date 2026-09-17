"""
WHAT:
    The structured fault model used by the Phase 4 Fault Injection Engine:
    fault type, severity, tunable parameters, injection condition and the
    expected detection behavior.

WHY:
    Phase 4 must inject faults that are deterministic, auditable and
    reversible. Modeling a fault as typed, validated data (instead of
    scattering ad-hoc mutation code) means:
      - the engine can decide strictly from data whether/when to inject,
      - every firing is recorded into a structured, inspectable history,
      - later phases (analysis / detection) can correlate observed
        symptoms to the exact fault that caused them via fault_id, type
        and severity.

HOW:
    - `FaultType` enumerates the ten supported injectable faults.
    - `FaultSeverity` grades how serious an injected fault is.
    - `FaultImpact` classifies which subsystem a fault affects: the
      READING produced by the simulator, the MQTT MESSAGE on the wire, or
      the CONNECTION/transport itself. Adapters use this to decide which
      fault set they evaluate.
    - `InjectionCondition` deterministically specifies WHEN a fault takes
      effect (absolute tick/publish-request indexes — never wall-clock
      time, so runs are reproducible).
    - `FaultParams` holds the tunable parameters; only the fields relevant
      to a particular fault type are used.
    - `ExpectedDetection` records what a later analysis phase should be
      able to observe once the framework behaves correctly.
    - `FaultSpec` is the immutable definition of one injectable fault.
    - `FaultRecord` is one entry of the execution history (a firing).
    - Precedence maps give deterministic tie-breaking when several faults
      are eligible at the same index.

HOW TO VERIFY:
    See tests/unit/test_fault_models.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FaultType(str, Enum):
    """The ten fault scenarios the engine can inject."""

    SENSOR_OUT_OF_RANGE = "SENSOR_OUT_OF_RANGE"
    SENSOR_UNDER_RANGE = "SENSOR_UNDER_RANGE"
    INVALID_SENSOR_DATA = "INVALID_SENSOR_DATA"
    MISSING_MESSAGE = "MISSING_MESSAGE"
    DELAYED_MESSAGE = "DELAYED_MESSAGE"
    DUPLICATE_MESSAGE = "DUPLICATE_MESSAGE"
    MQTT_DISCONNECT = "MQTT_DISCONNECT"
    MQTT_TIMEOUT = "MQTT_TIMEOUT"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    DEVICE_DISCONNECT = "DEVICE_DISCONNECT"


class FaultSeverity(str, Enum):
    """How severe an injected fault is (informational grading)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FaultImpact(str, Enum):
    """Which subsystem an injected fault affects."""

    READING = "READING"  # corrupts the reading produced by the simulator
    MESSAGE = "MESSAGE"  # corrupts / loses / duplicates the MQTT message
    CONNECTION = "CONNECTION"  # degrades the MQTT connection / transport


READING_FAULT_PRECEDENCE: dict[FaultType, int] = {
    FaultType.DEVICE_DISCONNECT: 0,
    FaultType.INVALID_SENSOR_DATA: 1,
    FaultType.SENSOR_UNDER_RANGE: 2,
    FaultType.SENSOR_OUT_OF_RANGE: 3,
}

TRANSPORT_FAULT_PRECEDENCE: dict[FaultType, int] = {
    FaultType.MQTT_DISCONNECT: 0,
    FaultType.MQTT_TIMEOUT: 1,
    FaultType.MISSING_MESSAGE: 2,
    FaultType.INVALID_PAYLOAD: 3,
    FaultType.DELAYED_MESSAGE: 4,
    FaultType.DUPLICATE_MESSAGE: 5,
}


class InjectionCondition(BaseModel):
    """
    Deterministic specification of WHEN a fault takes effect.

    Uses absolute tick / publish-request indexes (not wall-clock time) so
    behavior is perfectly reproducible run-to-run.
    """

    start_tick: int = Field(default=0, ge=0)
    end_tick: int | None = Field(
        default=None,
        ge=1,
        description="Exclusive upper bound. None = until the fault is deactivated.",
    )
    every_n: int | None = Field(
        default=None,
        ge=1,
        description="If set, the fault only fires every N-th index within the window.",
    )

    @model_validator(mode="after")
    def _end_after_start(self) -> "InjectionCondition":
        if self.end_tick is not None and self.end_tick <= self.start_tick:
            raise ValueError("end_tick must be greater than start_tick")
        return self

    def applies_at(self, index: int) -> bool:
        """True if the fault is effective at the given absolute index."""
        if index < self.start_tick:
            return False
        if self.end_tick is not None and index >= self.end_tick:
            return False
        if self.every_n is not None and (index - self.start_tick) % self.every_n != 0:
            return False
        return True

    def __contains__(self, index: int) -> bool:
        return self.applies_at(index)


class FaultParams(BaseModel):
    """Tunable parameters for a fault. Only the fields relevant to a fault's
    type are consulted; the rest keep their (harmless) defaults."""

    overshoot_c: float = Field(
        default=10.0,
        ge=0,
        description="SENSOR_OUT_OF_RANGE: injected value = max_temperature_c + overshoot_c",
    )
    undershoot_c: float = Field(
        default=10.0,
        ge=0,
        description="SENSOR_UNDER_RANGE: injected value = min_temperature_c - undershoot_c",
    )
    invalid_data_kind: Literal["nan", "inf"] = Field(
        default="nan",
        description="INVALID_SENSOR_DATA: what non-numeric value to emit while ONLINE",
    )
    delay_seconds: float = Field(
        default=1.0,
        ge=0,
        description="DELAYED_MESSAGE: how long to hold the message before publishing",
    )
    duplicate_count: int = Field(
        default=1,
        ge=1,
        le=10,
        description="DUPLICATE_MESSAGE: number of EXTRA copies of the same message",
    )
    invalid_payload_kind: Literal["malformed_json", "not_json", "wrong_schema"] = Field(
        default="malformed_json",
        description="INVALID_PAYLOAD: what kind of corrupt payload to publish",
    )


class ExpectedDetection(BaseModel):
    """What a later analysis / fault-detection phase should be able to observe."""

    impacted_subsystem: FaultImpact
    symptom: str = Field(
        description="Machine-readable symptom tag, e.g. 'reading.out_of_range'"
    )
    behavior: str = Field(
        description="Human-readable description of the expected observable behavior"
    )


class FaultSpec(BaseModel):
    """Immutable definition of one injectable fault."""

    model_config = {"frozen": True}

    fault_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    fault_type: FaultType
    description: str
    severity: FaultSeverity = FaultSeverity.MEDIUM
    injection_condition: InjectionCondition = Field(default_factory=InjectionCondition)
    params: FaultParams = Field(default_factory=FaultParams)
    expected_detection: ExpectedDetection
    enabled: bool = True

    @model_validator(mode="after")
    def _description_required(self) -> "FaultSpec":
        if not self.description.strip():
            raise ValueError("description must not be empty")
        return self


class FaultRecord(BaseModel):
    """One recorded firing of an injected fault (execution history entry)."""

    record_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    fault_id: str
    fault_type: FaultType
    severity: FaultSeverity
    tick_index: int = Field(
        ge=0,
        description="Index where the fault fired — sensor tick index or publisher "
        "message index, depending on the affected subsystem.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Virtual reading timestamp when available (deterministic), "
        "otherwise wall-clock time.",
    )
    detail: str = Field(default="")