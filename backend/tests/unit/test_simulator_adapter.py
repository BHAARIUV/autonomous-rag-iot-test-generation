"""
Phase 4 unit tests for FaultInjectedSimulator (the READING-impact fault
adapter). Uses only a real Phase 2 simulator plus the injector — no MQTT
and no broker required.
"""

import math

from app.faults import FaultInjector, make_fault
from app.faults.models import FaultParams, FaultType, InjectionCondition
from app.faults.simulator_adapter import FaultInjectedSimulator
from app.iot.models import SensorConfig, SensorStatus
from app.iot.simulator import TemperatureSensorSimulator

_CONFIG = SensorConfig(
    min_temperature_c=0.0,
    max_temperature_c=50.0,
    base_temperature_c=25.0,
    seed=1,
)


def _faulted_sim(config=None):
    injector = FaultInjector()
    sim = FaultInjectedSimulator(
        TemperatureSensorSimulator(config or _CONFIG), injector
    )
    return sim, injector


def test_out_of_range_injects_above_max():
    sim, injector = _faulted_sim()
    injector.inject(make_fault(FaultType.SENSOR_OUT_OF_RANGE))

    reading = sim.tick()

    assert reading.value_c == 60.0  # max=50 + overshoot=10
    assert reading.valid is False
    assert reading.status is SensorStatus.ONLINE
    assert reading.tick == 0
    assert sim.tick_count == 1


def test_under_range_injects_below_min():
    sim, injector = _faulted_sim()
    injector.inject(make_fault(FaultType.SENSOR_UNDER_RANGE))

    reading = sim.tick()

    assert reading.value_c == -10.0  # min=0 - undershoot=10
    assert reading.valid is False
    assert reading.status is SensorStatus.ONLINE


def test_invalid_data_injects_nan_while_online():
    sim, injector = _faulted_sim()
    injector.inject(make_fault(FaultType.INVALID_SENSOR_DATA))

    reading = sim.tick()

    assert reading.value_c != reading.value_c  # NaN check
    assert reading.valid is False
    assert reading.status is SensorStatus.ONLINE


def test_invalid_data_can_inject_infinity():
    sim, injector = _faulted_sim()
    injector.inject(
        make_fault(
            FaultType.INVALID_SENSOR_DATA, params=FaultParams(invalid_data_kind="inf")
        )
    )

    reading = sim.tick()

    assert reading.value_c == math.inf
    assert reading.valid is False
    assert reading.status is SensorStatus.ONLINE


def test_device_disconnect_reports_offline():
    sim, injector = _faulted_sim()
    injector.inject(make_fault(FaultType.DEVICE_DISCONNECT))

    reading = sim.tick()

    assert reading.status is SensorStatus.OFFLINE
    assert reading.valid is False
    assert reading.value_c != reading.value_c  # NaN placeholder
    assert sim.status is SensorStatus.ONLINE  # wrapper does not mutate sim state


def test_ticks_outside_window_are_unmodified_and_parity_with_plain_simulator():
    plain = TemperatureSensorSimulator(_CONFIG)
    sim, injector = _faulted_sim()
    injector.inject(
        make_fault(
            FaultType.SENSOR_OUT_OF_RANGE,
            injection_condition=InjectionCondition(start_tick=2, end_tick=3),
        )
    )

    plain_values = [plain.tick().value_c for _ in range(4)]
    sim_values = [sim.tick().value_c for _ in range(4)]

    # Only tick index 2 is meant to be faulted; ticks 0,1,3 must be identical
    # to the plain simulator's output.
    assert sim_values[2] == 60.0
    assert sim_values[0] == plain_values[0]
    assert sim_values[1] == plain_values[1]
    assert sim_values[3] == plain_values[3]


def test_deactivating_fault_restores_normal_readings():
    sim, injector = _faulted_sim()
    fault_id = injector.inject(make_fault(FaultType.SENSOR_OUT_OF_RANGE))

    assert sim.tick().valid is False
    injector.deactivate(fault_id)
    assert sim.tick().valid is True


def test_tick_count_propagates_regardless_of_fault():
    sim, injector = _faulted_sim()
    injector.inject(
        make_fault(
            FaultType.SENSOR_OUT_OF_RANGE,
            injection_condition=InjectionCondition(start_tick=1, end_tick=2),
        )
    )
    sim.tick()
    sim.tick()
    sim.tick()
    assert sim.tick_count == 3


def test_precedence_device_disconnect_beats_invalid_data():
    sim, injector = _faulted_sim()
    injector.inject(
        make_fault(
            FaultType.INVALID_SENSOR_DATA,
            fault_id="invalid",
            injection_condition=InjectionCondition(start_tick=0, end_tick=2),
        )
    )
    injector.inject(
        make_fault(
            FaultType.DEVICE_DISCONNECT,
            fault_id="device",
            injection_condition=InjectionCondition(start_tick=0, end_tick=2),
        )
    )

    reading = sim.tick()

    assert reading.status is SensorStatus.OFFLINE  # device wins


def test_history_records_each_firing_with_detail():
    sim, injector = _faulted_sim()
    fault_id = injector.inject(
        make_fault(
            FaultType.SENSOR_OUT_OF_RANGE,
            injection_condition=InjectionCondition(start_tick=0, end_tick=3),
        )
    )
    sim.tick()
    sim.tick()
    sim.tick()

    assert injector.count_for(fault_id) == 3
    assert [r.tick_index for r in injector.history] == [0, 1, 2]
    assert all("60.000" in r.detail for r in injector.history)
    assert all(r.timestamp is not None for r in injector.history)


def test_deterministic_replay_identical_setups():
    def run():
        injector = FaultInjector()
        sim = FaultInjectedSimulator(TemperatureSensorSimulator(_CONFIG), injector)
        injector.inject(
            make_fault(
                FaultType.SENSOR_OUT_OF_RANGE,
                fault_id="range",
                injection_condition=InjectionCondition(start_tick=0, end_tick=5, every_n=2),
            )
        )
        readings = [sim.tick() for _ in range(6)]
        return readings, [(r.tick_index, r.fault_type) for r in injector.history]

    first_readings, first_history = run()
    second_readings, second_history = run()

    assert first_readings == second_readings
    assert first_history == second_history
    # every-n=2: even tick indexes faulted, odd indexes normal.
    for index in (0, 2, 4):
        assert first_readings[index].value_c == 60.0
    for index in (1, 3, 5):
        assert 0.0 <= first_readings[index].value_c <= 50.0
        assert first_readings[index].valid is True