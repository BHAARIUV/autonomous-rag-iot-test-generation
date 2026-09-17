"""
Phase 12 — unit tests: dashboard service section builders against REAL data.
"""

from __future__ import annotations

import pytest

from app.dashboard import models as vm
from app.dashboard import provider, render
from app.dashboard.service import DashboardService
from app.refinement.models import (
    CoverageSnapshot,
    RefinementDecision,
    RefinementIteration,
    RefinementResult,
    StopReason,
)

REPORT = pytest.importorskip("app.reporting.models").FinalProjectReport


@pytest.fixture(scope="module")
def report():
    return provider.load_report_from_json()


@pytest.fixture(scope="module")
def svc():
    return DashboardService(provider.default_settings())


def _snap(req_pct: float, gap_count: int, covered: int = 1) -> CoverageSnapshot:
    return CoverageSnapshot(
        total_requirements=4, covered_requirements=covered,
        requirement_coverage=req_pct, total_test_cases=6, executed_test_cases=6,
        execution_coverage=100.0, total_faults=0, detected_faults=0,
        fault_detection_rate=0.0, gap_count=gap_count,
    )


class TestDataLoading:
    def test_load_real_report(self, report):
        assert len(report.requirements) >= 1
        assert len(report.phases) == 10
        assert report.summary.requirement_count >= 1
        assert report.test_summary.total >= 0

    def test_missing_report_raises(self):
        with pytest.raises(provider.NotAvailableError):
            provider.load_report_from_json("does/not/exist.json")

    def test_load_knowledge_catalog(self):
        catalog = provider.load_knowledge_catalog()
        assert catalog["documents"], "corpus should have documents"
        assert all("topic" in d for d in catalog["documents"])


class TestOverview:
    def test_project_summary(self, svc, report):
        redacted = provider.RedactedConfig(svc._cfg)
        ov = svc.build_overview(report, redacted)
        assert ov.project_name
        assert ov.current_phase == 13
        assert ov.completed_phases >= 13
        assert ov.generation_mode == "MOCK"
        assert ov.total_requirements == report.summary.requirement_count
        assert ov.total_test_cases == report.summary.test_case_count
        assert ov.passed == report.summary.passed_count


class TestRequirements:
    def test_coverage_statuses(self, svc, report):
        rows = svc.build_requirements(report)
        assert rows
        statuses = {r.coverage_status for r in rows}
        assert statuses <= {"COVERED", "PARTIALLY COVERED", "UNCOVERED"}
        for r in rows:
            assert r.requirement_id
            assert r.category
            assert r.description

    def test_missing_requirement_data(self, svc, report):
        rows = svc.build_requirements(report)
        assert all(isinstance(r.test_case_count, int) for r in rows)


class TestKnowledge:
    def test_requirement_knowledge_mapping(self, svc, report):
        catalog = provider.load_knowledge_catalog()
        k = svc.build_knowledge(catalog, report)
        assert k.document_count == len(catalog["documents"])
        # RETRIEVAL count is a real count of evidence chunks, never fabricated
        for m in k.requirement_mapping:
            assert m.retrieval_count == len(m.chunks)
        # no invented semantic quality metrics
        assert k.semantic_metrics is False


class TestGeneration:
    def test_mode_mock_and_validation(self, svc, report):
        redacted = provider.RedactedConfig(svc._cfg)
        g = svc.build_generation(report, redacted)
        assert g.generation_mode == "MOCK"
        assert g.total_generated == len(g.tests)
        for t in g.tests:
            assert t.generation_mode == "MOCK"
            assert t.validation_status in {"VALIDATED", "REJECTED", "PENDING",
                                           "Not available"}
            assert t.requirement_id


class TestExecution:
    def test_execution_summary(self, svc, report):
        e = svc.build_execution(report)
        assert e.execution_coverage is not None
        passed = e.passed or 0
        failed = e.failed or 0
        assert passed + failed >= 0
        # execution history reflects real per-test statuses
        for h in e.execution_history:
            assert h["status"] in {"PASS", "FAIL", "ERROR", "SKIPPED"}
            assert h["test_case_id"]


class TestFaults:
    def test_fault_summary_no_inference(self, svc, report):
        f = svc.build_fault_summary(report)
        assert f.total_faults is not None
        # detection state comes straight from evidence-backed report fields
        for fault in f.faults:
            assert fault.detection_status in {
                "DETECTED", "MISSED", "NOT_EXECUTED", "NOT_APPLICABLE",
                "Not available",
            }
            assert fault.fault_type


class TestRefinement:
    def test_refinement_unavailable_on_failure(self, svc, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("cannot compute")

        monkeypatch.setattr(provider, "compute_refinement", boom)
        rv = svc.build_refinement()
        assert rv.available is False

    def test_refinement_summary_maps_real_result(self, svc, monkeypatch):
        before = _snap(25.0, 2, covered=1)
        after = _snap(100.0, 0, covered=4)
        it = RefinementIteration(
            iteration_number=1, decision=RefinementDecision.REGENERATE,
            coverage_before=before, coverage_after=after, improvement=75.0,
            generated_test_case_ids=["TC-R1-001"], executed_ids=["TC-R1-001"],
        )
        result = RefinementResult(
            initial_coverage=before, final_coverage=after, final_gap_count=0,
            improvement_requirement_coverage=75.0,
            improvement_execution_coverage=0.0, improvement_fault_detection=0.0,
            iterations=[it], stop_reason=StopReason.TARGET_REACHED,
            total_generated=13, total_executed=13,
        )
        monkeypatch.setattr(provider, "compute_refinement", lambda *a, **k: result)
        rv = svc.build_refinement()
        assert rv.available is True
        assert rv.stop_reason == "TARGET_REACHED"
        assert rv.coverage_before == 25.0
        assert rv.coverage_after == 100.0
        assert rv.improvement_requirement_coverage == 75.0
        assert rv.total_generated == 13
        assert len(rv.iterations) == 1
        assert rv.iterations[0].decision == "REGENERATE"


class TestTraceability:
    def test_traceability_rows_use_real_ids(self, svc, report):
        t = svc.build_traceability(report)
        assert t.rows
        for row in t.rows:
            assert row.requirement_id
            assert isinstance(row.test_case_ids, list)
            assert row.coverage in {"COVERED", "PARTIALLY COVERED", "UNCOVERED"}


class TestFinalStatus:
    def test_phases_1_14_final_status(self, svc, report):
        fs = svc.build_final_status(report)
        by_num = {p.phase_number: p for p in fs.phases}
        assert by_num[13].status == "COMPLETE"
        assert by_num[14].status == "PENDING"
        assert all(by_num[i].status == "COMPLETE" for i in range(1, 13))
        assert fs.remaining_gaps is not None

    def test_final_test_result_from_report(self, svc, report):
        fs = svc.build_final_status(report)
        assert fs.final_test_result["total"] == report.test_summary.total
        assert fs.final_test_result["passed"] == report.test_summary.passed


class TestMissingDataRendering:
    def test_not_available_renders_for_absent_values(self):
        data = vm.DashboardData(
            overview=vm.OverviewView(project_name="p", total_requirements=None,
                                     passed=None, failed=None),
            knowledge=vm.KnowledgeView(),
            generation=vm.GenerationView(),
            execution=vm.ExecutionView(total_executed=None),
            fault_summary=vm.FaultSummaryView(),
            refinement=vm.RefinementView(available=False),
            traceability=vm.TraceabilityView(),
            final_status=vm.FinalStatusView(),
        )
        text = render.render_text(data)
        assert "Not available" in text
        html = render.render_html(data)
        assert "Not available" in html


class TestSecretProtection:
    def test_dashboard_never_surfaces_api_key(self, svc, report):
        from app.config import Settings

        secret = "sk-TOPSECRET-777"
        cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_MODEL="g",
                       LLM_API_KEY=secret, EMBEDDING_PROVIDER="local",
                       EMBEDDING_DIMENSION=256)
        red = provider.RedactedConfig(cfg)
        out = " ".join([red.redacted_api_key(), red.llm_provider])
        assert secret not in out
        assert secret not in red.redacted_api_key()
