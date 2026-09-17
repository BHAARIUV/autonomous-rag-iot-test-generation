"""
Phase 9 integration tests — full Phase 5 -> Phase 8 -> Phase 9 chain (MOCK, offline):

    Phase 5 requirement (temperature range -40..125 C)
        -> Phase 6 RAG retrieval (real shipped corpus, temp Chroma store)
        -> Phase 7 LLM test generation (MOCK provider)
        -> Phase 8 execution service (real PASS/FAIL/SKIPPED ExecutionResults)
        -> Phase 9 analysis (coverage + fault detection + gaps)

End-to-end contracts verified here:
- coverage consumes REAL Phase 8 results (never fabricated),
- requirement coverage / category coverage / interface coverage / fault
  detection / gaps are all derived from actual execution evidence,
- traceability survives from requirement -> test case -> result -> analysis,
- the summary matches hand-computed values for the deterministic scenario.

No API key, no network, no broker required (MQTT tests become honest SKIPPED
when the broker is down, and that is exactly what the analysis reports).
"""

import pytest

from app.analysis import AnalysisService
from app.config import Settings
from app.faults import FaultType, make_fault
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.testing import ExecutionService, TestActionType, make_action
from app.testing.models import TestStatus


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path / "chroma"),
        RAG_COLLECTION_NAME="int_analysis_knowledge",
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
    yield generator, executor, cfg
    rag.close()


def _range_spec():
    return (
        "Device: Temperature Sensor\n"
        "Range: -40 C to 125 C\n"
        "Accuracy: 0.5 C\n"
        "Sampling Interval: 1 s\n"
        "Communication Protocol: MQTT\n"
    )


def test_full_chain_analysis_uses_real_results(chain):
    generator, executor, _ = chain
    spec = ingest_text(_range_spec(), source="temperature_sensor.txt")
    reqs = spec.requirements
    requirement = {r.requirement_id: r for r in reqs}["REQ-001"]

    suite = generator.generate_for_requirement(requirement, top_k=4)
    results, summary = executor.execute_test_cases(suite.test_cases)

    # Phase 8 executed every generated case (device drives real outcomes)
    assert summary.total == len(suite.test_cases)
    assert all(r.status is TestStatus.PASS for r in results)

    # Known fault registry (Phase 4) for fault-detection analysis
    known_faults = [
        make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
    ]

    report = AnalysisService.analyze_execution_results(
        reqs, suite.test_cases, results, known_faults
    )

    # REQ-001 (RANGE) is fully covered by real PASS results.
    rc = next(c for c in report.requirement_coverage if c.requirement_id == "REQ-001")
    assert rc.covered is True
    assert rc.executed > 0
    assert rc.passed == rc.executed

    # Categories: the mock generator yields POSITIVE + 2 BOUNDARY + 2 NEGATIVE
    # (+ EQUIVALENCE). All executed.
    cats = {c.category for c in report.test_coverage.by_category}
    assert {"POSITIVE", "BOUNDARY", "NEGATIVE"} <= cats
    assert all(c.executed == c.total for c in report.test_coverage.by_category
               if c.total > 0)

    # Fault SENSOR_OUT_OF_RANGE was never injected in this suite -> FAULT gap.
    fc = next(f for f in report.fault_coverage if f.fault_type == "SENSOR_OUT_OF_RANGE")
    assert fc.injected_count == 0
    assert fc.detected is False
    assert any(g.type == "FAULT_NO_TEST" for g in report.gaps)


def test_fault_injection_result_detected_in_analysis(chain):
    _, executor, _ = chain
    # Real FAIL straight through the executor: injected out-of-range fault
    # + range assertion -> FAIL is the DETECTION signal.
    fault_result = executor.execute_actions(
        [
            make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
            make_action(TestActionType.READ_SENSOR),
            make_action(TestActionType.ASSERT_RANGE),
        ],
        test_case_id="TC-FAULT-001",
        requirement_id="REQ-001",
    )
    assert fault_result.status is TestStatus.FAIL

    known_faults = [
        make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
        make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISC"),
    ]

    report = AnalysisService.analyze_execution_results(
        [], [], [fault_result], known_faults
    )
    fc = next(f for f in report.fault_coverage if f.fault_type == "SENSOR_OUT_OF_RANGE")
    assert fc.injected_count == 1
    assert fc.detected_count == 1
    assert fc.detected is True
    assert fc.detection_rate == 100.0
    assert fc.related_test_cases == ["TC-FAULT-001"]

    # MQTT_DISCONNECT never injected -> FAULT_NO_TEST gap and 0% overall if
    # it were counted among totals (here it has no injections).
    mqtt_fc = next(f for f in report.fault_coverage if f.fault_type == "MQTT_DISCONNECT")
    assert mqtt_fc.injected_count == 0


def test_injected_but_undetected_fault_reported_as_missed(chain):
    _, executor, _ = chain
    # Raw READ alone (no assertion) -> the fault escapes undetected -> PASS.
    result = executor.execute_actions(
        [
            make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
            make_action(TestActionType.READ_SENSOR),
        ],
        test_case_id="TC-UNDETECTED",
        requirement_id="REQ-001",
    )
    assert result.status is TestStatus.PASS  # fault present but no assertion caught it

    known_faults = [make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR")]
    report = AnalysisService.analyze_execution_results([], [], [result], known_faults)
    fc = next(f for f in report.fault_coverage if f.fault_type == "SENSOR_OUT_OF_RANGE")
    assert fc.injected_count == 1
    assert fc.detected_count == 0
    assert fc.missed_count == 1
    assert fc.detected is False
    assert fc.detection_rate == 0.0
    assert any(g.type == "FAULT_NOT_DETECTED" for g in report.gaps)


def test_mqtt_skipped_reflected_as_interface_gap(chain):
    # Build a single MQTT test case whose execution is honestly SKIPPED
    # without a broker, and confirm the analysis reports an interface gap.
    _, executor, _ = chain
    from app.llm.models import (
        GenerationMetadata, TestCategory, TestCase, TestData, TestPriority, TestStep,
    )
    mqtt_case = TestCase(
        test_case_id="TC-MQTT-1",
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
    mqtt_result = executor.execute_test_case(mqtt_case)
    # Honest outcome: PASS with broker, SKIPPED without. Analysis must match.
    assert mqtt_result.status in (TestStatus.PASS, TestStatus.SKIPPED)

    report = AnalysisService.analyze_execution_results(
        [], [mqtt_case], [mqtt_result], []
    )
    ic = next(c for c in report.interface_coverage if c.protocol == "MQTT")
    assert ic.total == 1
    if mqtt_result.status is TestStatus.SKIPPED:
        assert ic.executed == 0
        assert ic.covered is False
        assert any(g.type == "INTERFACE_NO_EXECUTED_TEST" for g in report.gaps)
    else:
        assert ic.executed == 1
        assert ic.covered is True


def test_report_recommendations_derived_from_gaps(chain):
    _, executor, _ = chain
    known_faults = [make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT")]
    report = AnalysisService.analyze_execution_results([], [], [], known_faults)
    assert any("MQTT_DISCONNECT" in r for r in report.recommendations)
    assert report.summary.fault_detection_rate == 0.0
