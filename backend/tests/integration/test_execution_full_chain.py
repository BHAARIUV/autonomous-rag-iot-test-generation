"""
Phase 8 integration tests — the full Phase 5 -> Phase 8 chain (MOCK mode, offline):

    Phase 5 requirement (temperature range -40..125 C)
        -> Phase 6 RAG retrieval (real shipped corpus, temp Chroma store)
        -> Phase 7 LLM test generation (MOCK provider)
        -> Phase 8 execution service (safe, typed PASS/FAIL/ERROR/SKIPPED)

End-to-end contracts verified here are exactly the ones the demo shows:
- every generated test case executes without ever running generated code,
- BOUNDARY/NEGATIVE/EQUIVALENCE cases resolved against the real device bounds,
- the device's own rejection of out-of-range commands counts as a PASS,
- operator action chains (e.g. fault injection) produce genuine FAILs,
- traceability survives execution (result carries test_case_id + requirement_id).

No API key, no network, no broker required.
"""

import os

import pytest

from app.config import Settings
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.testing import ExecutionService
from app.testing.actions import TestActionType, make_action
from app.testing.models import TestStatus


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path / "chroma"),
        RAG_COLLECTION_NAME="int_execution_knowledge",
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


def _suite_for_requirement(generator, spec_text, requirement_id, *, source="temperature_sensor.txt"):
    spec = ingest_text(spec_text, source=source)
    requirement = {r.requirement_id: r for r in spec.requirements}[requirement_id]
    return generator.generate_for_requirement(requirement, top_k=4)


@pytest.fixture
def range_spec():
    return (
        "Device: Temperature Sensor\n"
        "Range: -40 C to 125 C\n"
        "Accuracy: 0.5 C\n"
        "Sampling Interval: 1 s\n"
        "Communication Protocol: MQTT\n"
    )


def test_phase5_to_phase8_full_chain_mock_executes_all(chain, range_spec):
    generator, executor, _ = chain
    suite = _suite_for_requirement(generator, range_spec, "REQ-001")
    assert len(suite.test_cases) == 6

    results, summary = executor.execute_test_cases(suite.test_cases)

    # execution completed without a crash and never executed generated code
    assert len(results) == 6
    assert summary.total == 6
    assert summary.passed == 6, summary.failed  # every generated case drives a real outcome
    assert all(r.status is TestStatus.PASS for r in results)

    # traceability survives execution
    for result, tc in zip(results, suite.test_cases):
        assert result.test_case_id == tc.test_case_id
        assert result.requirement_id == "REQ-001"


def test_boundary_cases_execute_against_real_device_bounds(chain, range_spec):
    generator, executor, _ = chain
    suite = _suite_for_requirement(generator, range_spec, "REQ-001")
    boundary = [tc for tc in suite.test_cases if tc.category.value == "BOUNDARY"]
    assert len(boundary) == 2
    assert {tc.test_data.inputs["input"] for tc in boundary} == {"-40", "125"}

    results, _ = executor.execute_test_cases(boundary)
    assert all(r.status is TestStatus.PASS for r in results)
    observed = {r.simulator_state.last_observed_value for r in results}
    assert 125.0 in observed and -40.0 in observed


def test_negative_case_device_correctly_rejects_and_passes(chain, range_spec):
    generator, executor, _ = chain
    suite = _suite_for_requirement(generator, range_spec, "REQ-001")
    negative = [tc for tc in suite.test_cases if tc.category.value == "NEGATIVE"]
    assert {tc.test_data.inputs["input"] for tc in negative} == {"-40.1", "125.1"}

    results, _ = executor.execute_test_cases(negative)
    for result, tc in zip(results, negative):
        assert result.status is TestStatus.PASS  # device rejected the bad input as expected
        assert result.simulator_state.commanded_value == float(tc.test_data.inputs["input"])


def test_generated_cases_never_execute_generated_code_directly(chain, range_spec):
    """The actions executed must all be from the closed, whitelisted action set."""
    generator, executor, _ = chain
    suite = _suite_for_requirement(generator, range_spec, "REQ-001")
    results, _ = executor.execute_test_cases(suite.test_cases)
    allowed = {a.value for a in TestActionType}
    for result in results:
        for evidence in result.execution_evidence:
            assert evidence.action in allowed
            assert result.status is not TestStatus.ERROR


def test_operator_fault_injection_chain_produces_genuine_fail(chain, range_spec):
    """
    A real FAIL straight through the executor: the operator injects an
    out-of-range fault, the actuator reads the faulted value (out of the
    declared bounds), and the range assertion fails loudly with a reason.
    """
    _, executor, _ = chain
    result = executor.execute_actions([
        make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
        make_action(TestActionType.READ_SENSOR),
        make_action(TestActionType.ASSERT_RANGE),
    ])
    assert result.status is TestStatus.FAIL
    assert "outside" in (result.failure_reason or "")
    assert any(
        e.action == "ASSERT_RANGE"
        and e.assertion_result is TestStatus.FAIL
        for e in result.execution_evidence
    )


def test_fault_reading_escapes_declared_bounds(chain, range_spec):
    """The fault really pushes the observed value beyond the declared bounds."""
    _, executor, _ = chain
    result = executor.execute_actions([
        make_action(TestActionType.INJECT_FAULT, fault_type="SENSOR_OUT_OF_RANGE", start_tick=0),
        make_action(TestActionType.READ_SENSOR),
    ])
    assert result.status is TestStatus.PASS  # raw read alone is not an assertion
    reading = result.simulator_state.last_observed_value
    assert reading > result.simulator_state.max_temperature_c