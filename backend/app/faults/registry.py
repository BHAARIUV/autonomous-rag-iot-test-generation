"""
WHAT:
    A catalog of pre-built fault definitions (one canonical default per
    FaultType) plus a factory that constructs a populated FaultSpec with
    sensible severity, description and expected-detection metadata, while
    letting callers override any part (params, injection condition, ...).

WHY:
    Later phases (test generation, autonomous refinement) will frequently
    need to construct standard faults — e.g. "SENSOR_OUT_OF_RANGE" or
    "MQTT_DISCONNECT". Centralizing the canonical defaults here means:
      - specs are always complete and self-describing (no missing
        description / expected detection),
      - names, severities and symptoms can be kept consistent across the
        whole framework,
      - tests and the demo only override what they actually need.

HOW:
    - FaultRegistry.make_fault(fault_type, **overrides) builds one spec.
    - FaultRegistry.default_specs() returns one spec per fault type with
      unique auto-generated ids.
    - A module-level make_fault convenience is re-exported for brevity.

HOW TO VERIFY:
    See tests/unit/test_fault_registry.py.
"""

from __future__ import annotations

import uuid

from app.faults.models import (
    ExpectedDetection,
    FaultImpact,
    FaultParams,
    FaultSeverity,
    FaultSpec,
    FaultType,
    InjectionCondition,
)

class FaultRegistry:
    """Catalog + factory of canonical fault definitions."""

    # (severity, description, impacted subsystem, symptom tag, expected behavior)
    _TYPE_DEFAULTS: dict[FaultType, tuple] = {
        FaultType.SENSOR_OUT_OF_RANGE: (
            FaultSeverity.HIGH,
            "The sensor reports a temperature above its configured maximum.",
            FaultImpact.READING,
            "reading.out_of_range_high",
            "A reading with value_c > max_temperature_c and valid=False.",
        ),
        FaultType.SENSOR_UNDER_RANGE: (
            FaultSeverity.HIGH,
            "The sensor reports a temperature below its configured minimum.",
            FaultImpact.READING,
            "reading.under_range_low",
            "A reading with value_c < min_temperature_c and valid=False.",
        ),
        FaultType.INVALID_SENSOR_DATA: (
            FaultSeverity.CRITICAL,
            "The sensor emits corrupt (non-numeric) data while ONLINE.",
            FaultImpact.READING,
            "reading.invalid_data",
            "A reading with valid=False and a non-numeric value while status is ONLINE.",
        ),
        FaultType.MISSING_MESSAGE: (
            FaultSeverity.HIGH,
            "A scheduled reading message is dropped and never reaches the subscriber.",
            FaultImpact.MESSAGE,
            "message.missing",
            "Fewer temperature messages than expected; a tick produces no publish.",
        ),
        FaultType.DELAYED_MESSAGE: (
            FaultSeverity.MEDIUM,
            "A reading message arrives later than its sampling interval allows.",
            FaultImpact.MESSAGE,
            "message.delayed",
            "A message arrives after a noticeable latency rather than immediately.",
        ),
        FaultType.DUPLICATE_MESSAGE: (
            FaultSeverity.MEDIUM,
            "The same reading message is published multiple times.",
            FaultImpact.MESSAGE,
            "message.duplicate",
            "The subscriber receives repeat copies of an identical message.",
        ),
        FaultType.MQTT_DISCONNECT: (
            FaultSeverity.CRITICAL,
            "The publisher loses its MQTT connection; no messages are sent.",
            FaultImpact.CONNECTION,
            "connection.disconnected",
            "Publishes are suppressed while active and no messages arrive.",
        ),
        FaultType.MQTT_TIMEOUT: (
            FaultSeverity.HIGH,
            "The broker becomes unresponsive; publish operations time out.",
            FaultImpact.CONNECTION,
            "connection.timeout",
            "A publish attempt is made but never completes / is never delivered.",
        ),
        FaultType.INVALID_PAYLOAD: (
            FaultSeverity.CRITICAL,
            "A corrupt message payload is published on the temperature topic.",
            FaultImpact.MESSAGE,
            "message.invalid_payload",
            "The subscriber rejects the payload and records it in invalid_messages.",
        ),
        FaultType.DEVICE_DISCONNECT: (
            FaultSeverity.CRITICAL,
            "The sensor device goes offline; readings report OFFLINE.",
            FaultImpact.READING,
            "device.disconnected",
            "Readings carry status=OFFLINE, valid=False and no temperature value.",
        ),
    }

    @classmethod
    def make_fault(
        cls,
        fault_type: FaultType,
        *,
        fault_id: str | None = None,
        severity: FaultSeverity | None = None,
        description: str | None = None,
        injection_condition: InjectionCondition | None = None,
        params: FaultParams | None = None,
        expected_detection: ExpectedDetection | None = None,
        enabled: bool = True,
    ) -> FaultSpec:
        """
        Build a fully populated FaultSpec for the given fault type using
        canonical metadata, allowing any field to be overridden.
        """
        default_severity, default_description, impact, symptom, behavior = (
            cls._TYPE_DEFAULTS[fault_type]
        )

        kwargs: dict = {
            "fault_type": fault_type,
            "description": description if description is not None else default_description,
            "severity": severity if severity is not None else default_severity,
            "enabled": enabled,
        }
        if fault_id is not None:
            kwargs["fault_id"] = fault_id
        if injection_condition is not None:
            kwargs["injection_condition"] = injection_condition
        if params is not None:
            kwargs["params"] = params
        if expected_detection is None:
            kwargs["expected_detection"] = ExpectedDetection(
                impacted_subsystem=impact,
                symptom=symptom,
                behavior=behavior,
            )
        else:
            kwargs["expected_detection"] = expected_detection

        return FaultSpec(**kwargs)

    @classmethod
    def default_specs(cls) -> list[FaultSpec]:
        """One canonical spec per fault type (dormant, unique ids)."""
        return [cls.make_fault(fault_type) for fault_type in FaultType]


make_fault = FaultRegistry.make_fault