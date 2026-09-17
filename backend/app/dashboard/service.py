"""
Phase 12 — DashboardService: folds REAL project data into the dashboard views.

WHY:
    A thin, read-only assembler. It takes the Phase 10 `FinalProjectReport`, the
    RAG knowledge catalog and the Phase 11 refinement result (all produced by the
    existing pipeline services) and maps them onto the typed view models that the
    renderer consumes. No business logic is duplicated: coverage/execution/fault
    numbers come straight from `report.coverage` / `report.summary`, execution
    statuses from real `ExecutionResult`s, fault detection states from the
    evidence-backed report faults, and refinement from the real Phase 11 result.
"""

from __future__ import annotations

from typing import Any

from app.dashboard import models as vm
from app.dashboard import provider
from app.reporting.models import FinalProjectReport

_PHASE_TITLES = {
    1: "Project setup & skeleton",
    2: "IoT temperature sensor simulator",
    3: "MQTT communication layer",
    4: "Fault injection engine",
    5: "Requirement extraction",
    6: "RAG knowledge base & retrieval",
    7: "LLM test generation + validation",
    8: "Automated test execution",
    9: "Coverage & fault analysis",
    10: "Final reporting & traceability",
    11: "Autonomous refinement loop",
    12: "Dashboard",
    13: "End-to-end integration",
    14: "Final testing, debugging, documentation",
}

COMPLETE_THROUGH = 13  # Phases 1-13 complete; 14 remains NOT STARTED.


def _na_str(v, fmt=lambda x: x) -> str:
    return str(fmt(v)) if v is not None and v != provider.MISSING else vm.not_available()


class DashboardService:
    """Builds every dashboard section from real project data (read-only)."""

    def __init__(self, cfg=None, report_path=None):
        self._cfg = cfg or provider.default_settings()
        self._report_path = report_path

    # ------------------------------------------------------------- helpers

    def _report(self) -> FinalProjectReport:
        return provider.load_report(self._cfg, self._report_path)

    # --------------------------------------------------------------- A. overview

    def build_overview(self, report: FinalProjectReport, redacted) -> vm.OverviewView:
        s = report.summary
        generation_mode = "MOCK" if redacted.mock_mode else "REAL LLM"
        phases = _build_phase_rows(report)
        current = COMPLETE_THROUGH
        completed = sum(1 for p in phases if p.status == "COMPLETE")
        return vm.OverviewView(
            project_name=report.project_name,
            project_id=report.project_id,
            project_status=report.status,
            current_phase=current,
            completed_phases=completed,
            total_phases=len(phases),
            total_requirements=_int_or_none(s.requirement_count),
            total_test_cases=_int_or_none(s.test_case_count),
            executed_tests=_int_or_none(s.executed_test_count),
            passed=_int_or_none(s.passed_count),
            failed=_int_or_none(s.failed_count),
            errors=_int_or_none(s.error_count),
            skipped=_int_or_none(s.skipped_count),
            generation_mode=generation_mode,
            analysis_id=report.analysis_id,
        )

    # -------------------------------------------------------- B. requirements

    def build_requirements(self, report: FinalProjectReport) -> list[vm.RequirementView]:
        rows: list[vm.RequirementView] = []
        for req in report.requirements:
            test_count = len(req.tests)
            if req.covered:
                coverage = "COVERED"
            elif test_count > 0:
                coverage = "PARTIALLY COVERED"
            else:
                coverage = "UNCOVERED"
            rows.append(vm.RequirementView(
                requirement_id=req.requirement_id,
                category=req.category,
                description=req.description,
                validation_status=_req_validation(req),
                test_case_count=test_count,
                coverage_status=coverage,
            ))
        return rows

    # ------------------------------------------------------- C. knowledge

    def build_knowledge(self, catalog: dict, report: FinalProjectReport) -> vm.KnowledgeView:
        docs = [
            vm.KnowledgeDocView(
                document_id=d["document_id"], title=d["title"], topic=d["topic"],
                source=d["source"], version=d["version"],
            )
            for d in catalog["documents"]
        ]
        mapping: list[vm.RequirementKnowledgeView] = []
        all_topics: set[str] = set()
        for req in report.requirements:
            topics: set[str] = set()
            sources: set[str] = set()
            chunks: list[str] = []
            for ev in req.spec_evidence:
                topics.add(ev.topic)
                sources.add(ev.source)
                chunks.append(ev.chunk_id)
            mapping.append(vm.RequirementKnowledgeView(
                requirement_id=req.requirement_id,
                retrieval_count=len(chunks),
                topics=sorted(topics),
                sources=sorted(sources),
                chunks=sorted(chunks),
            ))
            all_topics.update(topics)
        return vm.KnowledgeView(
            corpus_description=catalog["corpus_description"],
            corpus_version=catalog["corpus_version"],
            document_count=len(docs),
            semantic_metrics=False,  # no invented quality metrics
            documents=docs,
            requirement_mapping=mapping,
            retrieved_topics=sorted(all_topics),
        )

    # ----------------------------------------------------- D. generation

    def build_generation(self, report: FinalProjectReport, redacted) -> vm.GenerationView:
        mode = "MOCK" if redacted.mock_mode else "REAL LLM"
        tests: list[vm.GeneratedTestView] = []
        for req in report.requirements:
            for t in req.tests:
                tests.append(vm.GeneratedTestView(
                    test_case_id=t.test_case_id,
                    requirement_id=t.requirement_id,
                    category=t.category,
                    priority=t.priority,
                    generation_mode=mode,
                    validation_status=t.validation_status.value,
                ))
        return vm.GenerationView(
            total_generated=len(tests),
            generation_mode=mode,
            tests=tests,
        )

    # ---------------------------------------------------- E. execution

    def build_execution(self, report: FinalProjectReport) -> vm.ExecutionView:
        status_counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIPPED": 0}
        history: list[dict] = []
        total_executed = 0
        for req in report.requirements:
            for t in req.tests:
                for ex in t.executions:
                    st = ex.execution_status
                    status_counts[st] = status_counts.get(st, 0) + 1
                    history.append({
                        "test_case_id": t.test_case_id,
                        "status": st,
                        "execution_id": ex.execution_id,
                    })
                if t.has_executed:
                    total_executed += 1
        return vm.ExecutionView(
            total_executed=_int_or_none(report.coverage.executed_test_cases),
            passed=status_counts.get("PASS"),
            failed=status_counts.get("FAIL"),
            errors=status_counts.get("ERROR"),
            skipped=status_counts.get("SKIPPED"),
            execution_coverage=_float_or_none(report.coverage.execution_coverage),
            execution_history=history,
        )

    # ------------------------------------------------------- F. faults

    def build_fault_summary(self, report: FinalProjectReport) -> vm.FaultSummaryView:
        faults = [
            vm.FaultView(
                fault_id=f.fault_id,
                fault_type=f.fault_type,
                detection_status=f.detection_status.value,
                injection_status=f.injection_status.value,
                requirement_ids=f.requirement_ids,
                related_test_case_ids=f.related_test_case_ids,
                detection_evidence=f.detection_evidence or vm.not_available(),
                execution_result=f.execution_result or vm.not_available(),
            )
            for f in report.faults
        ]
        missed = None
        det = _int_or_none(report.coverage.detected_faults)
        total = _int_or_none(report.coverage.total_faults)
        if det is not None and total is not None:
            missed = total - det
        return vm.FaultSummaryView(
            total_faults=total,
            detected_faults=det,
            missed_faults=missed,
            fault_detection_rate=_float_or_none(report.coverage.fault_detection_rate),
            faults=faults,
        )

    # --------------------------------------------- G. refinement

    def build_refinement(self) -> vm.RefinementView:
        try:
            result = provider.compute_refinement(self._cfg)
        except Exception:
            return vm.RefinementView(available=False)
        iterations = [
            vm.RefinementIterationView(
                iteration_number=it.iteration_number,
                decision=it.decision.value,
                gap_type=it.selected_gap.gap_type if it.selected_gap else vm.not_available(),
                generated=len(it.generated_test_case_ids),
                executed=len(it.executed_ids),
                coverage_before=_float_or_none(it.coverage_before.requirement_coverage),
                coverage_after=_float_or_none(it.coverage_after.requirement_coverage),
                improvement=round(float(it.improvement), 2),
            )
            for it in result.iterations
        ]
        return vm.RefinementView(
            available=True,
            stop_reason=result.stop_reason.value,
            gaps_before=result.initial_coverage.gap_count,
            gaps_after=result.final_coverage.gap_count,
            coverage_before=_float_or_none(result.initial_coverage.requirement_coverage),
            coverage_after=_float_or_none(result.final_coverage.requirement_coverage),
            improvement_requirement_coverage=round(
                float(result.improvement_requirement_coverage), 2),
            total_generated=result.total_generated,
            total_executed=result.total_executed,
            iterations=iterations,
        )

    # ----------------------------------------------- H. traceability

    def build_traceability(self, report: FinalProjectReport) -> vm.TraceabilityView:
        rows: list[vm.TraceabilityRowView] = []
        for req in report.requirements:
            rag_evidence = [ev.chunk_id for ev in req.spec_evidence]
            test_ids = [t.test_case_id for t in req.tests]
            exec_ids: list[str] = []
            statuses: set[str] = set()
            for t in req.tests:
                for ex in t.executions:
                    exec_ids.append(ex.execution_id)
                    statuses.add(ex.execution_status)
            fault_types = _collect_fault_types(req)
            rows.append(vm.TraceabilityRowView(
                requirement_id=req.requirement_id,
                rag_evidence_count=len(rag_evidence),
                rag_evidence=rag_evidence,
                test_case_ids=test_ids,
                validation_status=(
                    "VALIDATED" if test_ids else vm.not_available()),
                execution_ids=exec_ids,
                execution_status=", ".join(sorted(statuses)) if statuses else vm.not_available(),
                fault_types=fault_types,
                fault_detection="Detected" if req.covered else vm.not_available(),
                coverage="COVERED" if req.covered else (
                    "PARTIALLY COVERED" if test_ids else "UNCOVERED"),
                refined=bool(test_ids),
            ))
        return vm.TraceabilityView(rows=rows)

    # ---------------------------------------------- I. final status

    def build_final_status(self, report: FinalProjectReport) -> vm.FinalStatusView:
        phases = _build_phase_rows(report)
        return vm.FinalStatusView(
            phases=phases,
            final_test_result={
                "total": _int_or_none(report.test_summary.total),
                "passed": _int_or_none(report.test_summary.passed),
                "failed": _int_or_none(report.test_summary.failed),
                "errors": _int_or_none(report.test_summary.errors),
                "skipped": _int_or_none(report.test_summary.skipped),
            },
            requirement_coverage=_float_or_none(report.coverage.requirement_coverage),
            execution_coverage=_float_or_none(report.coverage.execution_coverage),
            fault_detection=_float_or_none(report.coverage.fault_detection_rate),
            remaining_gaps=_int_or_none(report.coverage.gap_count),
            known_limitations=list(report.summary.known_limitations),
        )

    # ------------------------------------------------------------- entry

    def build(self) -> vm.DashboardData:
        report = self._report()
        redacted = provider.RedactedConfig(self._cfg)
        catalog = provider.load_knowledge_catalog(self._cfg)
        return vm.DashboardData(
            overview=self.build_overview(report, redacted),
            requirements=self.build_requirements(report),
            knowledge=self.build_knowledge(catalog, report),
            generation=self.build_generation(report, redacted),
            execution=self.build_execution(report),
            fault_summary=self.build_fault_summary(report),
            refinement=self.build_refinement(),
            traceability=self.build_traceability(report),
            final_status=self.build_final_status(report),
        )


def _int_or_none(v) -> int | None:
    return int(v) if v is not None and v != provider.MISSING else None


def _float_or_none(v) -> float | None:
    return float(v) if v is not None and v != provider.MISSING else None


def _req_validation(req) -> str:
    statuses = {t.validation_status.value for t in req.tests}
    if not statuses:
        return vm.not_available()
    if statuses == {"VALIDATED"}:
        return "VALIDATED"
    return ", ".join(sorted(statuses))


def _collect_fault_types(req) -> list[str]:
    types: set[str] = set()
    for t in req.tests:
        for ex in t.executions:
            for ft in ex.fault_types_injected:
                types.add(ft)
    return sorted(types)


def _build_phase_rows(report: FinalProjectReport) -> list[vm.PhaseStatusView]:
    report_verification = {
        p.phase_number: p.verification for p in report.phases
    }
    rows: list[vm.PhaseStatusView] = []
    for num in range(1, 15):
        title = _PHASE_TITLES.get(num, vm.not_available())
        if num <= COMPLETE_THROUGH:
            status = "COMPLETE"
        else:
            status = "PENDING"  # Phase 14 remains NOT STARTED
        rows.append(vm.PhaseStatusView(
            phase_number=num,
            title=title,
            status=status,
            verification=report_verification.get(num, ""),
        ))
    return rows


__all__ = ["DashboardService", "COMPLETE_THROUGH"]
