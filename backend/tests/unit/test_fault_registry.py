"""
Phase 4 unit tests for the fault catalog / factory (FaultRegistry and the
make_fault convenience function).
"""

from app.faults import make_fault
from app.faults.models import (
    ExpectedDetection,
    FaultImpact,
    FaultParams,
    FaultSeverity,
    FaultSpec,
    FaultType,
    InjectionCondition,
)
from app.faults.registry import FaultRegistry


def test_make_fault_supports_all_types():
    for fault_type in FaultType:
        spec = make_fault(fault_type)
        assert isinstance(spec, FaultSpec)
        assert spec.fault_type is fault_type
        assert spec.description.strip()
        assert spec.expected_detection.symptom.strip()
        assert spec.expected_detection.behavior.strip()


def test_make_fault_severity_defaults():
    assert make_fault(FaultType.SENSOR_OUT_OF_RANGE).severity is FaultSeverity.HIGH
    assert make_fault(FaultType.SENSOR_UNDER_RANGE).severity is FaultSeverity.HIGH
    assert make_fault(FaultType.INVALID_SENSOR_DATA).severity is FaultSeverity.CRITICAL
    assert make_fault(FaultType.MISSING_MESSAGE).severity is FaultSeverity.HIGH
    assert make_fault(FaultType.DELAYED_MESSAGE).severity is FaultSeverity.MEDIUM
    assert make_fault(FaultType.DUPLICATE_MESSAGE).severity is FaultSeverity.MEDIUM
    assert make_fault(FaultType.MQTT_DISCONNECT).severity is FaultSeverity.CRITICAL
    assert make_fault(FaultType.MQTT_TIMEOUT).severity is FaultSeverity.HIGH
    assert make_fault(FaultType.INVALID_PAYLOAD).severity is FaultSeverity.CRITICAL
    assert make_fault(FaultType.DEVICE_DISCONNECT).severity is FaultSeverity.CRITICAL


def test_make_fault_impact_classification():
    reading_types = {
        FaultType.SENSOR_OUT_OF_RANGE,
        FaultType.SENSOR_UNDER_RANGE,
        FaultType.INVALID_SENSOR_DATA,
        FaultType.DEVICE_DISCONNECT,
    }
    connection_types = {FaultType.MQTT_DISCONNECT, FaultType.MQTT_TIMEOUT}
    for fault_type in FaultType:
        impact = make_fault(fault_type).expected_detection.impacted_subsystem
        if fault_type in reading_types:
            assert impact is FaultImpact.READING
        elif fault_type in connection_types:
            assert impact is FaultImpact.CONNECTION
        else:
            assert impact is FaultImpact.MESSAGE


def test_make_fault_overrides_params():
    spec = make_fault(FaultType.DELAYED_MESSAGE, params=FaultParams(delay_seconds=3.0))
    assert spec.params.delay_seconds == 3.0


def test_make_fault_overrides_injection_condition():
    spec = make_fault(
        FaultType.MISSING_MESSAGE,
        injection_condition=InjectionCondition(start_tick=2, end_tick=5),
    )
    assert spec.injection_condition.start_tick == 2
    assert spec.injection_condition.end_tick == 5


def test_make_fault_overrides_metadata():
    custom_detection = ExpectedDetection(
        impacted_subsystem=FaultImpact.MESSAGE,
        symptom="custom.symptom",
        behavior="custom behavior",
    )
    spec = make_fault(
        FaultType.SENSOR_OUT_OF_RANGE,
        fault_id="route-01",
        severity=FaultSeverity.LOW,
        description="custom description",
        expected_detection=custom_detection,
        enabled=False,
    )
    assert spec.fault_id == "route-01"
    assert spec.severity is FaultSeverity.LOW
    assert spec.description == "custom description"
    assert spec.expected_detection is custom_detection
    assert spec.enabled is False


def test_default_specs_cover_all_types_with_unique_ids():
    specs = FaultRegistry.default_specs()
    assert len(specs) == len(FaultType)
    assert {s.fault_type for s in specs} == set(FaultType)
    ids = [s.fault_id for s in specs]
    assert len(set(ids)) == len(ids)