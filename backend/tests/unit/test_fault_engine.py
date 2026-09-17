"""
Phase 4 unit tests for the FaultInjector engine: registration, activation,
enable/disable, deterministic decision-making, precedence and execution
history. Pure engine tests — no simulator or MQTT involved.
"""

import pytest

from app.faults import make_fault
from app.faults.engine import FaultInjector
from app.faults.models import FaultImpact, FaultType, InjectionCondition


def _range_spec(**overrides):
    return make_fault(FaultType.SENSOR_OUT_OF_RANGE, **overrides)


def test_add_fault_returns_fault_id_and_registers():
    injector = FaultInjector()
    spec = _range_spec()
    fault_id = injector.add_fault(spec)
    assert fault_id == spec.fault_id
    assert injector.spec(fault_id) is spec


def test_add_fault_rejects_duplicate_id():
    injector = FaultInjector()
    spec = _range_spec(fault_id="same-id")
    injector.add_fault(spec)
    with pytest.raises(ValueError):
        injector.add_fault(_range_spec(fault_id="same-id"))


def test_new_fault_is_dormant_until_activated():
    injector = FaultInjector()
    fault_id = injector.add_fault(_range_spec())
    assert injector.is_active(fault_id) is False
    assert injector.should_inject(fault_id, 0) is False


def test_activate_then_should_inject_within_window():
    injector = FaultInjector()
    fault_id = injector.inject(_range_spec())
    assert injector.is_active(fault_id) is True
    assert injector.should_inject(fault_id, 0) is True
    assert injector.should_inject(fault_id, 99) is True


def test_should_inject_respects_window():
    injector = FaultInjector()
    fault_id = injector.add_fault(
        _range_spec(
            injection_condition=InjectionCondition(start_tick=2, end_tick=4)
        )
    )
    injector.activate(fault_id)
    assert injector.should_inject(fault_id, 1) is False
    assert injector.should_inject(fault_id, 2) is True
    assert injector.should_inject(fault_id, 3) is True
    assert injector.should_inject(fault_id, 4) is False


def test_disabled_fault_cannot_be_activated():
    injector = FaultInjector()
    fault_id = injector.add_fault(_range_spec(enabled=False))
    with pytest.raises(ValueError):
        injector.activate(fault_id)
    assert injector.is_active(fault_id) is False
    assert injector.should_inject(fault_id, 0) is False


def test_set_enabled_false_disables_and_deactivates_active_fault():
    injector = FaultInjector()
    fault_id = injector.inject(_range_spec())
    assert injector.should_inject(fault_id, 0) is True
    injector.set_enabled(fault_id, False)
    assert injector.is_active(fault_id) is False
    assert injector.should_inject(fault_id, 0) is False


def test_deactivate_stops_injection_but_keeps_registration():
    injector = FaultInjector()
    fault_id = injector.inject(_range_spec())
    injector.deactivate(fault_id)
    assert injector.is_active(fault_id) is False
    assert injector.should_inject(fault_id, 0) is False
    assert injector.spec(fault_id).fault_id == fault_id


def test_unknown_fault_nevers_injects_and_raises_on_activate():
    injector = FaultInjector()
    assert injector.should_inject("missing", 0) is False
    with pytest.raises(KeyError):
        injector.activate("missing")
    with pytest.raises(KeyError):
        injector.record("missing", 0)


def test_record_appends_history_with_snapshot():
    injector = FaultInjector()
    spec = _range_spec()
    fault_id = injector.inject(spec)
    record = injector.record(fault_id, 5, detail="boom")
    assert len(injector.history) == 1
    assert injector.history[0] is record
    assert record.fault_id == fault_id
    assert record.fault_type is spec.fault_type
    assert record.severity is spec.severity
    assert record.tick_index == 5
    assert record.detail == "boom"


def test_count_for_tracks_firings():
    injector = FaultInjector()
    fault_id = injector.inject(_range_spec())
    injector.record(fault_id, 1)
    injector.record(fault_id, 2)
    injector.record(fault_id, 3)
    assert injector.count_for(fault_id) == 3


def test_reset_deactivates_all_and_clears_history():
    injector = FaultInjector()
    first = injector.inject(_range_spec())
    second = injector.inject(_range_spec(fault_id="other", severity=None))
    injector.record(first, 0)
    injector.record(second, 0)
    injector.reset()
    assert injector.is_active(first) is False
    assert injector.is_active(second) is False
    assert injector.history == []
    assert injector.active_faults() == []


def test_active_faults_filters_by_impact():
    injector = FaultInjector()
    reading_id = injector.inject(_range_spec())
    conn_id = injector.inject(
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="conn-fault")
    )
    assert {s.fault_id for s in injector.active_faults()} == {
        reading_id,
        conn_id,
    }
    assert [s.fault_id for s in injector.active_faults(FaultImpact.READING)] == [
        reading_id
    ]
    assert [
        s.fault_id for s in injector.active_faults(FaultImpact.CONNECTION)
    ] == [conn_id]


def test_sensor_fault_at_respects_precedence():
    injector = FaultInjector()
    injector.inject(
        make_fault(
            FaultType.INVALID_SENSOR_DATA,
            fault_id="invalid",
            injection_condition=InjectionCondition(start_tick=0, end_tick=3),
        )
    )
    injector.inject(
        make_fault(
            FaultType.DEVICE_DISCONNECT,
            fault_id="device",
            injection_condition=InjectionCondition(start_tick=0, end_tick=3),
        )
    )
    winner = injector.sensor_fault_at(1)
    assert winner.fault_id == "device"  # DEVICE_DISCONNECT outranks INVALID data


def test_sensor_fault_at_ignores_window_and_returns_none_for_transport_faults():
    injector = FaultInjector()
    injector.inject(
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="conn")
    )
    assert injector.sensor_fault_at(0) is None
    assert injector.transport_fault_at(0).fault_id == "conn"


def test_sensor_fault_at_honors_condition_window():
    injector = FaultInjector()
    injector.inject(
        _range_spec(
            fault_id="range",
            injection_condition=InjectionCondition(start_tick=1, end_tick=2),
        )
    )
    assert injector.sensor_fault_at(0) is None
    assert injector.sensor_fault_at(1).fault_id == "range"
    assert injector.sensor_fault_at(2) is None


def test_deterministic_decisions_for_identical_specs():
    def run():
        injector = FaultInjector()
        injector.inject(
            make_fault(
                FaultType.SENSOR_OUT_OF_RANGE,
                fault_id="range",
                injection_condition=InjectionCondition(start_tick=0, end_tick=4, every_n=2),
            )
        )
        return [injector.should_inject("range", i) for i in range(6)]

    assert run() == run() == [True, False, True, False, False, False]