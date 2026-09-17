"""
Phase 9 — interactive demo of Coverage & Fault Analysis.

Builds the existing Temperature Sensor scenario end-to-end with offline
(MOCK) generation + Phase 8 execution, then runs Phase 9 analysis and prints
the computed coverage / fault-detection / gap numbers. Nothing here is
hard-coded — every percentage is derived from REAL results.

Scenario:
    REQ-001 temperature range -40..125 C
        -> mock-generated suite: POSITIVE + BOUNDARY(min) + BOUNDARY(max)
                                 + NEGATIVE(below) + NEGATIVE(above) + EQUIVALENCE
        -> Phase 8 execution  (all PASS)
        -> one fault-injection test: SENSOR_OUT_OF_RANGE  -> genuine FAIL
        -> known faults registered: SENSOR_OUT_OF_RANGE, MQTT_DISCONNECT
             (SENSOR_OUT_OF_RANGE is injected + detected
              MQTT_DISCONNECT is known but never tested -> FAULT_NO_TEST gap)
        -> one generated-but-never-executed test         -> TEST_GENERATED_NOT_EXECUTED gap
        -> one MQTT communication test (SKIPPED if broker down
             -> INTERFACE_NO_EXECUTED_TEST gap, else PASS)

HOW TO RUN:
    from the project root:  python -m app.analysis.demo
"""

from __future__ import annotations

from app.analysis import AnalysisService
from app.config import Settings
from app.faults import FaultType, make_fault
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.llm.models import (
    GenerationMetadata,
    TestCase,
    TestCategory,
    TestData,
    TestPriority,
    TestStep,
)
from app.rag.service import RagService
from app.testing import ExecutionService, TestActionType, make_action
from app.testing.models import TestStatus

_SPEC = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Accuracy: 0.5 C\n"
    "Sampling Interval: 1 s\n"
    "Communication Protocol: MQTT\n"
)


def _unexecuted_case() -> TestCase:
    """A test that is generated but deliberately NOT executed -> a gap."""
    return TestCase(
        test_case_id="TC-UNEXEC-001",
        requirement_id="REQ-001",
        title="Generated but never run (coverage gap)",
        objective="Demonstrate a generated-but-never-executed test.",
        category=TestCategory.BOUNDARY,
        priority=TestPriority.HIGH,
        preconditions=[],
        test_steps=[TestStep(step_number=1, action="Drive the device input to exactly -40 C.")],
        expected_result="device accepts -40 C",
        test_data=TestData(inputs={"input": "-40"}, expected={"status": "VALID"}),
        protocol="SENSOR",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


def _fault_case() -> TestCase:
    """The SENSOR_OUT_OF_RANGE fault-detection test (executed via direct
    actions; the TestCase object carries category/protocol traceability)."""
    return TestCase(
        test_case_id="TC-FAULT-001",
        requirement_id="REQ-001",
        title="Fault injection: SENSOR_OUT_OF_RANGE",
        objective="Detect an injected out-of-range reading via the range assertion.",
        category=TestCategory.NEGATIVE,
        priority=TestPriority.HIGH,
        preconditions=[],
        test_steps=[
            TestStep(step_number=1, action="Inject a SENSOR_OUT_OF_RANGE fault."),
            TestStep(step_number=2, action="Read the sensor."),
            TestStep(step_number=3, action="Assert the reading is within range."),
        ],
        expected_result="The out-of-range reading fails the assertion.",
        test_data=TestData(),
        protocol="SENSOR",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


def run_demo() -> None:
    cfg = Settings(_env_file=None, LLM_PROVIDER="mock", LLM_MODEL="mock-llm",
                   EMBEDDING_PROVIDER="local", EMBEDDING_DIMENSION=256,
                   RAG_TOP_K=4)
    rag = RagService(settings_=cfg)
    rag.index_knowledge_base()
    generator = GenerationService(settings_=cfg, rag_service=rag)
    executor = ExecutionService(settings_=cfg)

    spec = ingest_text(_SPEC, source="temperature_sensor.txt")
    requirement = {r.requirement_id: r for r in spec.requirements}["REQ-001"]
    suite = generator.generate_for_requirement(requirement, top_k=4)

    results, summary = executor.execute_test_cases(suite.test_cases)
    fault_case = _fault_case()
    fault_result = executor.execute_actions(
        [
            make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
            make_action(TestActionType.READ_SENSOR),
            make_action(TestActionType.ASSERT_RANGE),
        ],
        test_case_id="TC-FAULT-001",
        requirement_id="REQ-001",
    )
    results.append(fault_result)

    mqtt = _mqtt_case()
    mqtt_result = executor.execute_test_case(mqtt)
    results.append(mqtt_result)

    all_test_cases = list(suite.test_cases) + [_unexecuted_case()] + [fault_case, mqtt]

    known_faults = [
        make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISCONNECT"),
    ]

    report = AnalysisService.analyze_execution_results(
        [requirement], all_test_cases, results, known_faults
    )

    print("\n=== Phase 9 — Coverage & Fault Analysis demo ===\n")
    print(f"analysis_id : {report.analysis_id}")
    print(f"timestamp   : {report.timestamp.isoformat()}\n")

    print("--- Execution (Phase 8, from real results) ---")
    _executed = [r for r in results if r.status in (TestStatus.PASS, TestStatus.FAIL)]
    print(f"    executed  : {len(_executed)}   "
          f"passed : {sum(1 for r in results if r.status is TestStatus.PASS)}   "
          f"failed : {sum(1 for r in results if r.status is TestStatus.FAIL)}")
    if mqtt_result.status is TestStatus.SKIPPED:
        print("    mqtt test : SKIPPED (no broker)  -> INTERFACE gap")

    s = report.summary
    print("\n--- CoverageSummary ---")
    print(f"    total requirements   : {s.total_requirements}")
    print(f"    covered requirements : {s.covered_requirements}")
    print(f"    requirement coverage : {s.requirement_coverage}%")
    print(f"    total test cases     : {s.total_test_cases}")
    print(f"    executed test cases  : {s.executed_test_cases}")
    print(f"    execution coverage   : {s.execution_coverage}%")
    print(f"    pass rate            : {s.pass_rate}%")
    print(f"    total faults         : {s.total_faults}")
    print(f"    detected faults      : {s.detected_faults}")
    print(f"    fault detection rate : {s.fault_detection_rate}%")
    print(f"    gaps identified      : {s.gap_count}")

    print("\n--- Test-category coverage ---")
    for cat in report.test_coverage.by_category:
        print(f"    {cat.category:<12} total={cat.total} executed={cat.executed} "
              f"passed={cat.passed} failed={cat.failed} skipped={cat.skipped}")

    print("\n--- Interface coverage ---")
    for ic in report.interface_coverage:
        print(f"    {ic.interface:<16} total={ic.total} executed={ic.executed} covered={ic.covered}")

    print("\n--- Fault coverage ---")
    for fc in report.fault_coverage:
        print(f"    {fc.fault_type:<22} injected={fc.injected_count} detected={fc.detected_count} "
              f"detection={fc.detection_rate}%")

    print("\n--- Gaps ---")
    for g in report.gaps:
        print(f"    [{g.severity}] {g.gap_id} {g.type}")
        print(f"          {g.description}")

    print("\n--- Recommendations ---")
    for r in report.recommendations:
        print(f"    - {r}")
    print()


def _mqtt_case() -> TestCase:
    """An MQTT communication test; PASS with broker, honest SKIPPED without."""
    return TestCase(
        test_case_id="TC-MQTT-001",
        requirement_id="REQ-001",
        title="MQTT publish/validate",
        objective="Verify schema-conforming publication over MQTT.",
        category=TestCategory.COMMUNICATION,
        priority=TestPriority.HIGH,
        preconditions=["MQTT broker reachable."],
        test_steps=[
            TestStep(step_number=1, action="Subscribe to the device topic."),
            TestStep(step_number=2, action="Trigger a device publication."),
            TestStep(step_number=3, action="Validate the received JSON payload against the expected schema."),
        ],
        expected_result="A valid JSON payload arrives on the topic.",
        test_data=TestData(expected={"received": "CONFORMANT"}),
        protocol="MQTT",
        interface="iot/sensor/temperature",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="demo", timestamp="demo",
        ),
    )


if __name__ == "__main__":
    run_demo()
