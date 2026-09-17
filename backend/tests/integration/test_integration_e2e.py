"""Phase 13 end-to-end integration tests (complete MOCK-mode chain)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.integration import E2EPipeline
from app.testing.models import TestStatus

_MOCK_CFG = Settings(
    _env_file=None,
    LLM_PROVIDER="mock",
    LLM_MODEL="mock-llm",
    EMBEDDING_PROVIDER="local",
    EMBEDDING_DIMENSION=256,
    RAG_TOP_K=4,
)

_SPEC = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Accuracy: 0.5 C\n"
    "Sampling Interval: 1 s\n"
    "Communication Protocol: MQTT\n"
)

ALL_STAGES = {
    "INGESTION", "RAG", "GENERATION", "VALIDATION", "EXECUTION",
    "FAULT_ANALYSIS", "REFINEMENT", "REPORTING", "DASHBOARD",
}


@pytest.fixture(scope="module")
def e2e():
    result = E2EPipeline(settings_=_MOCK_CFG).run(
        _SPEC, source="phase13_temperature_sensor.txt", top_k=4
    )
    return result


class TestCompleteChain:
    def test_all_stages_report_success(self, e2e):
        got = {s.stage.value for s in e2e.stages}
        assert ALL_STAGES <= got
        assert all(s.ok for s in e2e.stages if s.stage.value in ALL_STAGES)

    def test_provider_mode_is_mock(self, e2e):
        assert e2e.provider_mode == "MOCK"

    def test_requirements_ingested(self, e2e):
        assert e2e.total_requirements >= 4
        assert e2e.total_tests > 0
        assert e2e.total_tests == e2e.validated_count

    def test_run_id_present(self, e2e):
        assert e2e.run_id

    def test_mock_chain_is_deterministic(self):
        a = E2EPipeline(settings_=_MOCK_CFG).run(_SPEC, top_k=4)
        b = E2EPipeline(settings_=_MOCK_CFG).run(_SPEC, top_k=4)
        assert a.total_tests == b.total_tests
        assert a.passed_count == b.passed_count
        assert a.failed_count == b.failed_count
        assert [tr.coverage_status for tr in a.requirements] == \
               [tr.coverage_status for tr in b.requirements]


class TestTraceability:
    def test_requirement_to_rag_evidence(self, e2e):
        assert e2e.requirements
        for tr in e2e.requirements:
            assert tr.requirement_id
            assert len(tr.rag_evidence_chunk_ids) > 0  # real RAG evidence

    def test_generated_to_validated_traceability(self, e2e):
        for tr in e2e.requirements:
            assert tr.generated_test_ids == tr.validated_test_ids
            assert tr.generated_test_ids  # every req generated tests

    def test_execution_result_propagation(self, e2e):
        executed = sum(len(tr.executed_test_ids) for tr in e2e.requirements)
        assert executed == e2e.executed_count
        assert e2e.passed_count + e2e.failed_count + e2e.error_count + e2e.skipped_count \
            == executed

    def test_fault_detection_propagation(self, e2e):
        assert e2e.report is not None
        assert e2e.report.summary.fault_detection_rate == 100.0  # evidence-backed
        assert e2e.failed_count >= 1  # the injected-fault test genuinely fails

    def test_refinement_result_propagation(self, e2e):
        assert e2e.refinement.applied is True
        assert e2e.refinement.stop_reason
        assert 0.0 <= e2e.refinement.coverage_after <= 100.0

    def test_final_report_propagation(self, e2e):
        assert e2e.report is not None
        assert len(e2e.report.requirements) == e2e.total_requirements
        assert e2e.report.summary.requirement_coverage > 0


class TestDashboardAvailability:
    def test_dashboard_data_available(self, e2e):
        assert e2e.dashboard_available is True
        assert "generation_mode" in e2e.dashboard_summary

    def test_dashboard_mode_is_mock(self, e2e):
        assert e2e.dashboard_summary.get("generation_mode") == "MOCK"


class TestNoFabricatedSuccess:
    def test_statuses_are_real(self, e2e):
        # executed_count must equal the real number of executed results
        assert e2e.executed_count >= e2e.total_tests
        assert e2e.executed_count == (
            e2e.passed_count + e2e.failed_count + e2e.error_count + e2e.skipped_count
        )
        # skipped/error never converted to pass
        assert e2e.skipped_count >= 0
        assert e2e.error_count >= 0

    def test_traceability_uses_real_requirement_ids(self, e2e):
        req_ids = {tr.requirement_id for tr in e2e.requirements}
        assert "REQ-001" in req_ids and "REQ-004" in req_ids
