"""
Phase 8 — interactive demo of the IoT test execution engine.

WHY:
    A human-readable walkthrough is the fastest way to see what the engine
    does: it translates Phase 7-style test specifications into the closed
    `TestAction` set, executes them deterministically against the simulated
    IoT environment, and reports each result as PASS / FAIL / ERROR / SKIPPED
    with evidence.

WHAT:
    1  Nominal operation                      -> EXPECTED PASS
    2  Minimum boundary (-40 C)              -> EXPECTED PASS
    3  Maximum boundary (125 C)              -> EXPECTED PASS
    4  Below minimum (-40.1 C)               -> EXPECTED PASS (device flags invalid)
    5  Above maximum (125.1 C)               -> EXPECTED PASS (device flags invalid)
    6  Sensor offline                        -> EXPECTED PASS (invalid reported)
    7  Offline -> recovery                   -> EXPECTED PASS
    8  Fault injection: SENSOR_OUT_OF_RANGE  -> EXPECTED FAIL (assertion not met)
    9  Unsupported step in a test case       -> EXPECTED EXECUTION ERROR
    10 MQTT publish/subscribe/validate       -> PASS if broker reachable, else SKIPPED

HOW TO RUN:
    from the project root:  python -m app.testing.demo
"""

from __future__ import annotations

from app.config import Settings
from app.llm.models import (
    GenerationMetadata,
    TestCategory,
    TestCase,
    TestData,
    TestPriority,
    TestStep,
)
from app.testing import (
    ExecutionResult,
    ExecutionService,
    ExecutionSummary,
    TestActionType,
    TestStatus,
    interpret_test_case,
    make_action,
)

_SEED_STEPS = [  # canonical Phase 7 mock vocabulary
    "Set the device input to the nominal value within the declared operating envelope.",
    "Trigger a measurement.",
    "Observe the reported value and device status.",
]


def _case(case_id: str, steps: list[str], expected: dict | None = None,
          inputs: dict | None = None) -> TestCase:
    return TestCase(
        test_case_id=case_id,
        requirement_id="DEMO-REQ-01",
        title=case_id,
        objective="Demo scenario for the execution engine.",
        category=TestCategory.POSITIVE,
        priority=TestPriority.MEDIUM,
        preconditions=[],
        test_steps=[
            TestStep(step_number=i + 1, action=text) for i, text in enumerate(steps)
        ],
        expected_result="demo",
        test_data=TestData(inputs=inputs or {}, expected=expected or {}),
        protocol="SENSOR",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


def _actions_line(case: TestCase) -> str:
    return " -> ".join(a.action.value for a in interpret_test_case(case))


def _label(result: ExecutionResult, expectation: str) -> str:
    hit = result.status.value == expectation
    mark = "OK " if hit else "!! "
    return f"{mark}(expected {expectation}, got {result.status.value})"


def run_demo() -> None:
    settings_ = Settings(_env_file=None)
    service = ExecutionService(settings_=settings_)
    print("\n=== Phase 8 — IoT Test Execution Engine demo ===\n")
    print(f"Config: max_duration={settings_.execution_max_duration_seconds}s, "
          f"max_wait={settings_.execution_max_wait_seconds}s\n")

    scenarios = [
        (
            "1 Nominal operation",
            _case("DEMO-01", _SEED_STEPS, {"status": "OK"}, {"input": "25"}),
            "PASS",
        ),
        (
            "2 Minimum boundary -40 C",
            _case("DEMO-02",
                  ["Drive the device input to exactly -40 C.", "Trigger a measurement and read the result."],
                  {"status": "VALID", "edge": "MIN"}, {"input": "-40"}),
            "PASS",
        ),
        (
            "3 Maximum boundary 125 C",
            _case("DEMO-03",
                  ["Drive the device input to exactly 125 C.", "Trigger a measurement and read the result."],
                  {"status": "VALID", "edge": "MAX"}, {"input": "125"}),
            "PASS",
        ),
        (
            "4 Below minimum -40.1 C",
            _case("DEMO-04",
                  ["Drive the device input to -40.1 C, below the minimum.", "Trigger a measurement and check the device response."],
                  {"status": "INVALID", "reason": "BELOW_MIN"}, {"input": "-40.1"}),
            "PASS",
        ),
        (
            "5 Above maximum 125.1 C",
            _case("DEMO-05",
                  ["Drive the device input to 125.1 C, above the maximum.", "Trigger a measurement and check the device response."],
                  {"status": "INVALID", "reason": "ABOVE_MAX"}, {"input": "125.1"}),
            "PASS",
        ),
        (
            "6 Sensor offline",
            _case("DEMO-06",
                  ["Take the device offline / disconnect it from the network.", "Let it capture measurements during the outage."],
                  {"status": "INVALID"}),
            "PASS",
        ),
        (
            "7 Offline then recovery",
            _case("DEMO-07",
                  ["Take the device offline / disconnect it from the network.",
                   "Bring the network back and observe reconnection.",
                   "Trigger a measurement."],
                  {"status": "OK"}),
            "PASS",
        ),
    ]

    # Fault-injection scenario executed with explicit actions (deterministic).
    results: list[ExecutionResult] = []
    for title, test_case, expected in scenarios:
        result = service.execute_test_case(test_case)
        results.append(result)
        print(f"[{title}]")
        print(f"    actions : {_actions_line(test_case)}")
        print(f"    status  : {result.status.value}  {_label(result, expected)}")
        if result.failure_reason:
            print(f"    why     : {result.failure_reason}")

    fault_result = service.execute_actions(
        [
            make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
            make_action(TestActionType.READ_SENSOR),
            make_action(TestActionType.ASSERT_RANGE),
        ],
        test_case_id="DEMO-08",
        requirement_id="DEMO-REQ-01",
    )
    results.append(fault_result)
    print("[8 Fault injection: SENSOR_OUT_OF_RANGE]")
    print("    actions : INJECT_FAULT -> READ_SENSOR -> ASSERT_RANGE")
    print(f"    status  : {fault_result.status.value}  {_label(fault_result, 'FAIL')}")
    if fault_result.failure_reason:
        print(f"    why     : {fault_result.failure_reason}")

    bad = _case("DEMO-09", ["Do something completely unsupported."])
    bad_result = service.execute_test_case(bad)
    results.append(bad_result)
    print("[9 Unsupported step in a test case]")
    print(f"    actions : => UnsupportedActionError rejected safely")
    print(f"    status  : {bad_result.status.value}  {_label(bad_result, 'ERROR')}")

    mqtt_status_expect = "PASS" if _broker_running(settings_) else "SKIPPED"
    mqtt = _case(
        "DEMO-10",
        ["Subscribe to the device topic.",
         "Trigger a device publication.",
         "Validate the received JSON payload against the expected schema."],
        {"received": "CONFORMANT"},
    )
    mqtt_result = service.execute_test_case(mqtt)
    results.append(mqtt_result)
    print("[10 MQTT publish / subscribe / validate]")
    print(f"    actions : {_actions_line(mqtt)}")
    print(f"    status  : {mqtt_result.status.value}  {_label(mqtt_result, mqtt_status_expect)}")
    if mqtt_result.status is TestStatus.SKIPPED and mqtt_result.failure_reason:
        print(f"    why     : {mqtt_result.failure_reason}")

    summary = ExecutionSummary.from_execution_results(results)
    print("\n=== Summary (from actual results only) ===")
    print(f"    total   : {summary.total}")
    print(f"    passed  : {summary.passed}")
    print(f"    failed  : {summary.failed}")
    print(f"    errors  : {summary.errors}")
    print(f"    skipped : {summary.skipped}")
    print(f"    pass    : {summary.pass_rate}%")
    if summary.failure_details:
        print("    failures:")
        for d in summary.failure_details:
            print(f"      - {d.test_case_id}: {d.status.value} — {d.reason[:80]}")
    print()


def _broker_running(settings_) -> bool:
    """Cheap probe: can we connect a raw socket to the configured broker port?"""
    import socket

    try:
        with socket.create_connection(
            (settings_.mqtt_broker_host, settings_.mqtt_broker_port), timeout=0.5
        ):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    run_demo()