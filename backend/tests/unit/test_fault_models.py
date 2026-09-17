"""
Phase 4 unit tests for the structured fault model: FaultType, FaultSeverity,
FaultImpact, InjectionCondition, FaultParams, FaultSpec, FaultRecord. These
are pure data-model tests — no simulator, no MQTT, no broker.
"""

import pytest
from pydantic import ValidationError

from app.faults.models import (
    ExpectedDetection,
    FaultImpact,
    FaultParams,
    FaultRecord,
    FaultSeverity,
    FaultSpec,
    FaultType,
    InjectionCondition,
)


def _spec(**overrides) -> FaultSpec:
    base = {
        "fault_type": FaultType.MQTT_DISCONNECT,
        "description": "test fault",
        "severity": FaultSeverity.MEDIUM,
        "expected_detection": ExpectedDetection(
            impacted_subsystem=FaultImpact.CONNECTION,
            symptom="connection.disconnected",
            behavior="publishes are suppressed",
        ),
    }
    base.update(overrides)
    return FaultSpec(**base)


def test_all_ten_fault_types_supported():
    expected = [
        "SENSOR_OUT_OF_RANGE",
        "SENSOR_UNDER_RANGE",
        "INVALID_SENSOR_DATA",
        "MISSING_MESSAGE",
        "DELAYED_MESSAGE",
        "DUPLICATE_MESSAGE",
        "MQTT_DISCONNECT",
        "MQTT_TIMEOUT",
        "INVALID_PAYLOAD",
        "DEVICE_DISCONNECT",
    ]
    assert [t.value for t in FaultType] == expected


def test_injection_condition_default_applies_everywhere():
    cond = InjectionCondition()
    for index in (0, 1, 5, 100):
        assert cond.applies_at(index)


def test_injection_condition_window_is_half_open():
    cond = InjectionCondition(start_tick=2, end_tick=5)
    assert not cond.applies_at(0)
    assert not cond.applies_at(1)
    assert cond.applies_at(2)
    assert cond.applies_at(4)
    assert not cond.applies_at(5)


def test_injection_condition_every_n_stride():
    cond = InjectionCondition(start_tick=1, end_tick=10, every_n=3)
    assert [i for i in range(10) if cond.applies_at(i)] == [1, 4, 7]


def test_injection_condition_rejects_end_not_after_start():
    with pytest.raises(ValidationError):
        InjectionCondition(start_tick=5, end_tick=5)
    with pytest.raises(ValidationError):
        InjectionCondition(start_tick=5, end_tick=4)


def test_fault_params_validate_counts_and_delays():
    with pytest.raises(ValidationError):
        FaultParams(duplicate_count=0)
    with pytest.raises(ValidationError):
        FaultParams(delay_seconds=-1.0)
    with pytest.raises(ValidationError):
        FaultParams(overshoot_c=-5.0)


def test_fault_spec_auto_generates_unique_ids():
    assert _spec().fault_id != _spec().fault_id


def test_fault_spec_allows_explicit_id():
    spec = _spec(fault_id="fixed-id")
    assert spec.fault_id == "fixed-id"


def test_fault_spec_requires_non_blank_description():
    with pytest.raises(ValidationError):
        _spec(description="   ")


def test_fault_spec_defaults():
    spec = _spec()
    assert spec.enabled is True
    assert spec.injection_condition == InjectionCondition()
    assert spec.params == FaultParams()
    assert spec.severity is FaultSeverity.MEDIUM


def test_fault_spec_is_immutable():
    spec = _spec()
    with pytest.raises(ValidationError):
        spec.description = "mutated"


def test_fault_record_holds_snapshot_fields():
    rec = FaultRecord(
        fault_id="f1",
        fault_type=FaultType.MISSING_MESSAGE,
        severity=FaultSeverity.HIGH,
        tick_index=3,
        detail="dropped",
    )
    assert rec.record_id
    assert rec.fault_type is FaultType.MISSING_MESSAGE
    assert rec.severity is FaultSeverity.HIGH
    assert rec.tick_index == 3
    assert rec.detail == "dropped"
    assert rec.timestamp is not None