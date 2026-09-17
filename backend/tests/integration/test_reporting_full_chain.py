"""
Phase 10 integration tests — the full traceability chain (MOCK, offline):

    Phase 5 requirement (temperature range -40..125 C)
        -> Phase 6 RAG retrieval (real shipped corpus, temp Chroma store)
        -> Phase 7 LLM test generation (MOCK provider)
        -> Phase 8 execution service (real PASS/FAIL/SKIPPED ExecutionResults)
        -> Phase 4/8 fault injection results
        -> Phase 9 analysis (coverage + fault detection + gaps)
        -> Phase 10 final project report (end-to-end traceability)

End-to-end contracts verified here:
- the final report links every requirement -> test case -> execution -> fault
  by REAL ids (never fabricated),
- the same coverage numbers appear in the final report and in Phase 9's
  analysis (single source of truth),
- fault detection is strictly evidence-backed: DETECTED only on a FAIL that
  injected the fault; NOT_EXECUTED when never injected — never inferred,
- the report is valid, serializable JSON and carries the whole phase list.

No API key, no network, no broker required (MQTT tests become honest SKIPPED
when the broker is down, and the report reflects that).
"""

import json

import pytest

from app.config import Settings
from app.faults import FaultType, make_fault
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.reporting import FinalReportService
from app.reporting.models import FaultDetectionStatus, InjectionStatus
from app.testing import ExecutionService, TestActionType, make_action


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path / "chroma"),
        RAG_COLLECTION_NAME="int_reporting_knowledge",
        RAG_CHUNK_SIZE=600,
        RAG_CHUNK_OVERLAP=80,
        RAG_TOP_K=4,
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
    )


@pytest.fixture
def chain(tmp_path):
    cfg = _settings(tmp_path)
    rag = RagService(settings_=cfg)
    assert rag.index_knowledge_base().document_count == 12
    generator = GenerationService(settings_=cfg, rag_service=rag)
    executor = ExecutionService(settings_=cfg)
    yield generator, executor, cfg, tmp_path
    rag.close()


def _range_spec():
    return (
        "Device: Temperature Sensor\n"
        "Range: -40 C to 125 C\n"
        "Accuracy: 0.5 C\n"
        "Sampling Interval: 1 s\n"
        "Communication Protocol: MQTT\n"
    )


def _make_mqtt_case():
    from app.llm.models import (
        GenerationMetadata, TestCategory, TestCase, TestData, TestPriority, TestStep,
    )

    return TestCase(
        test_case_id="TC-MQTT-001",
        requirement_id="REQ-004",
        title="MQTT publish/validate",
        objective="verify MQTT publication",
        category=TestCategory.COMMUNICATION,
        priority=TestPriority.HIGH,
        preconditions=["MQTT broker reachable."],
        test_steps=[
            TestStep(step_number=1, action="Subscribe to the device topic."),
            TestStep(step_number=2, action="Trigger a device publication."),
            TestStep(step_number=3, action="Validate the received JSON payload against the expected schema."),
        ],
        expected_result="valid payload on topic",
        test_data=TestData(expected={"received": "CONFORMANT"}),
        protocol="MQTT",
        interface="iot/sensor/temperature",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="test", timestamp="test",
        ),
    )


def _make_fault_case():
    from app.llm.models import (
        GenerationMetadata, TestCategory, TestCase, TestData, TestPriority, TestStep,
    )

    return TestCase(
        test_case_id="TC-FAULT-001",
        requirement_id="REQ-001",
        title="Fault injection: SENSOR_OUT_OF_RANGE",
        objective="detect an injected out-of-range reading",
        category=TestCategory.NEGATIVE,
        priority=TestPriority.HIGH,
        preconditions=[],
        test_steps=[
            TestStep(step_number=1, action="Inject a SENSOR_OUT_OF_RANGE fault."),
            TestStep(step_number=2, action="Read the sensor."),
            TestStep(step_number=3, action="Assert the reading is within range."),
        ],
        expected_result="out-of-range fails the assertion",
        test_data=TestData(),
        protocol="SENSOR",
        generation_metadata=GenerationMetadata(
            provider="mock", model="mock", generation_mode="mock",
            prompt_version="test", timestamp="test",
        ),
    )


def test_final_report_traceability_links_real_ids(chain):
    generator, executor, _, tmp_path = chain
    spec = ingest_text(_range_spec(), source="temperature_sensor.txt")
    reqs = spec.requirements
    requirement = {r.requirement_id: r for r in reqs}["REQ-001"]

    suite = generator.generate_for_requirement(requirement, top_k=4)
    results, _ = executor.execute_test_cases(suite.test_cases)

    # Add a fault-injecting FAIL (detection) + an MQTT case (PASS or SKIPPED).
    fault_case = _make_fault_case()
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

    mqtt_case = _make_mqtt_case()
    mqtt_result = executor.execute_test_case(mqtt_case)
    results.append(mqtt_result)

    all_test_cases = list(suite.test_cases) + [fault_case, mqtt_case]

    known_faults = [
        make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISC"),
    ]

    from app.reporting.models import FinalTestSummary

    report = FinalReportService.generate_final_report(
        requirements=reqs,
        test_cases=all_test_cases,
        results=results,
        fault_specs=known_faults,
        test_summary=FinalTestSummary(
            total=1, passed=1, failed=0, errors=0, skipped=0
        ),
        known_limitations=["test limitation"],
    )

    assert len(report.phases) == 10
    assert all(p.status.value == "COMPLETE" for p in report.phases)

    # Requirement traceability: REQ-001 covered by real executed results.
    req1 = next(r for r in report.requirements if r.requirement_id == "REQ-001")
    assert req1.covered is True
    assert any(t.test_case_id == "TC-FAULT-001" for t in req1.tests)

    # Fault traceability: DETECTED (evidence-backed FAIL) / NOT_EXECUTED.
    by_type = {f.fault_type: f for f in report.faults}
    assert by_type["SENSOR_OUT_OF_RANGE"].detection_status is FaultDetectionStatus.DETECTED
    assert by_type["SENSOR_OUT_OF_RANGE"].injection_status is InjectionStatus.INJECTED
    assert by_type["SENSOR_OUT_OF_RANGE"].execution_result == "FAIL"
    assert "TC-FAULT-001" in by_type["SENSOR_OUT_OF_RANGE"].related_test_case_ids
    assert by_type["MQTT_DISCONNECT"].detection_status is FaultDetectionStatus.NOT_EXECUTED

    # Coverage single-source-of-truth matches Phase 9 region (50%: REQ-001, REQ-004).
    assert report.summary.requirement_coverage == report.coverage.requirement_coverage

    # Serializable + loads from disk as produced by the writers.
    json_path = FinalReportService.write_json_report(report, tmp_path / "final_report.json")
    md_path = FinalReportService.write_markdown_report(report, tmp_path / "final_report.md")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["_schema"] == "autonomous-rag-iot-final-report/v1"
    assert any(f["fault_type"] == "SENSOR_OUT_OF_RANGE" for f in data["faults"])
    assert "Phase Completion" in md_path.read_text(encoding="utf-8")


def test_final_report_detection_never_inferred(chain):
    _, executor, _, tmp_path = chain
    known_faults = [make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT")]

    from app.reporting.models import FinalTestSummary

    report = FinalReportService.generate_final_report(
        requirements=[],
        test_cases=[],
        results=[],
        fault_specs=known_faults,
        test_summary=FinalTestSummary(
            total=0, passed=0, failed=0, errors=0, skipped=0
        ),
    )
    (ftrace,) = report.faults
    assert ftrace.detection_status is FaultDetectionStatus.NOT_EXECUTED
    assert "cannot be inferred" in ftrace.detection_evidence
