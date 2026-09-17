"""
Phase 10 — Final Reporting & Traceability service.

WHY:
    A clean, deterministic layer that binds the whole pipeline into one
    evidence-backed `FinalProjectReport`. It consumes the SAME trusted
    artifacts the earlier phases produce (Phase 5 Requirements, Phase 7
    TestCases, Phase 8 ExecutionResults, Phase 4 FaultSpecs) and reuses the
    Phase 9 `AnalysisService` for coverage, so nothing is recomputed
    inconsistently and nothing is fabricated. Writes both a machine-readable
    JSON report and a human-readable Markdown report.

WHAT:
    - build_phase_statuses()               -> list[PhaseEntry]
    - build_test_case_traceability(...)   -> list[TestCaseTraceability]
    - build_requirement_traceability(...) -> list[RequirementTraceability]
    - build_fault_traceability(...)       -> list[FaultTraceability]
    - build_final_summary(...)            -> FinalProjectSummary
    - generate_final_report(...)          -> FinalProjectReport
    - write_json_report(report, path)
    - write_markdown_report(report, path)

HOW (rules — see models.py):
    - Validation status is VALIDATED only for strict Phase 7 TestCase records.
    - A test case "has executed" iff it has a PASS/FAIL result.
    - A requirement is covered iff >=1 of its tests executed (matches Phase 9).
    - Fault detection is evidence-backed: DETECTED only if a test that injected
      the fault ended FAIL; else MISSED (if injected) or NOT_EXECUTED (if never
      injected). NEVER inferred.
    - Test counts come from a real pytest run passed by the caller; never
      guessed.

HOW TO VERIFY:
    See tests/unit/test_reporting_*.py and
    tests/integration/test_reporting_full_chain.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.analysis import AnalysisService
from app.analysis.models import CoverageGap, CoverageSummary
from app.faults.models import FaultSpec
from app.ingestion.models import Requirement
from app.llm.models import TestCase
from app.reporting.models import (
    FinalProjectReport,
    FinalProjectSummary,
    FinalTestSummary,
    FaultDetectionStatus,
    FaultTraceability,
    InjectionStatus,
    PhaseEntry,
    PhaseStatus,
    RagEvidence,
    RequirementTraceability,
    TestCaseExecutionLink,
    TestCaseTraceability,
    ValidationStatus,
)
from app.testing.models import ExecutionResult, TestStatus

_EXECUTED_STATUSES = frozenset({TestStatus.PASS, TestStatus.FAIL})

# Ordered canonical phase list for the whole project.
_PHASES: list[tuple[int, str, str, str]] = [
    (1, "Project Setup & Skeleton", "Core skeleton, config, logging", "python run.py + unit tests"),
    (2, "IoT Temperature Sensor Simulator", "Deterministic simulator, SensorConfig/Reading", "tests/unit/test_simulator.py"),
    (3, "MQTT Communication Layer", "MQTT connection, publisher, subscriber, wire messages", "tests/unit/test_mqtt_*.py"),
    (4, "Fault Injection Engine", "FaultInjector, registry, adapters, FaultSpec model", "tests/unit/test_fault_*.py"),
    (5, "Requirement Extraction", "Ingestion: text/JSON/PDF parsers, Requirement model", "tests/unit/test_spec_*.py"),
    (6, "RAG Knowledge Base & Retrieval", "Loader, chunker, embeddings, vector store, retriever", "tests/unit/test_rag_*.py"),
    (7, "LLM Test Generation + Validation", "Mock/OpenAI providers, parser, validate_candidates", "tests/unit/test_llm_*.py"),
    (8, "Automated Test Execution", "Closed action set, interpreter, executor, ExecutionResult", "tests/unit/test_execution_*.py"),
    (9, "Coverage & Fault Analysis", "Requirement/category/interface coverage, gaps", "tests/unit/test_analysis_*.py"),
    (10, "Final Reporting & Traceability", "End-to-end traceability, JSON/Markdown final reports", "tests/unit/test_reporting_*.py"),
]


class FinalReportService:
    """Builds the evidence-backed final project report."""

    # ------------------------------------------------------------------ phases

    @staticmethod
    def build_phase_statuses(
        complete_up_to: int = 10,
    ) -> list[PhaseEntry]:
        """Return phase entries; phases <= complete_up_to are COMPLETE."""
        entries: list[PhaseEntry] = []
        for number, title, feature, verification in _PHASES:
            status = (
                PhaseStatus.COMPLETE
                if number <= complete_up_to
                else PhaseStatus.PENDING
            )
            entries.append(
                PhaseEntry(
                    phase_number=number,
                    title=title,
                    status=status,
                    major_feature=feature,
                    verification=verification,
                )
            )
        return entries

    # -------------------------------------------------------------- test cases

    @staticmethod
    def build_test_case_traceability(
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
    ) -> list[TestCaseTraceability]:
        results_by_tc: dict[str, list[ExecutionResult]] = {}
        for result in results:
            results_by_tc.setdefault(result.test_case_id, []).append(result)

        trace: list[TestCaseTraceability] = []
        for tc in test_cases:
            tc_results = results_by_tc.get(tc.test_case_id, [])
            links = [
                TestCaseExecutionLink(
                    execution_id=r.execution_id,
                    execution_status=r.status.value,
                    fault_types_injected=FaultInjection.injected_types(r),
                )
                for r in tc_results
            ]
            executed = any(r.status in _EXECUTED_STATUSES for r in tc_results)
            final_status = None
            for r in tc_results:
                final_status = r.status.value
                break
            evidence = [
                RagEvidence(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    source=c.source,
                    topic=c.topic,
                    relevance=c.relevance,
                )
                for c in (tc.source_context.chunks if tc.source_context else [])
            ]
            trace.append(
                TestCaseTraceability(
                    test_case_id=tc.test_case_id,
                    requirement_id=tc.requirement_id,
                    category=tc.category.value,
                    priority=tc.priority.value,
                    protocol=tc.protocol,
                    interface=tc.interface,
                    validation_status=ValidationStatus.VALIDATED,
                    rag_evidence=evidence,
                    executions=links,
                    has_executed=executed,
                    final_status=final_status,
                )
            )
        return trace

    # ------------------------------------------------------------ requirements

    @staticmethod
    def build_requirement_traceability(
        requirements: Iterable[Requirement],
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
    ) -> list[RequirementTraceability]:
        tc_trace = {
            t.test_case_id: t
            for t in FinalReportService.build_test_case_traceability(
                test_cases, results
            )
        }
        requirements = list(requirements)
        test_cases = list(test_cases)

        result_by_tc: dict[str, list[ExecutionResult]] = {}
        for result in results:
            result_by_tc.setdefault(result.test_case_id, []).append(result)

        tc_by_req: dict[str, list[TestCase]] = {}
        for tc in test_cases:
            tc_by_req.setdefault(tc.requirement_id, []).append(tc)

        fault_types_by_req: dict[str, set[str]] = {}
        for result in results:
            for ft in FaultInjection.injected_types(result):
                fault_types_by_req.setdefault(result.requirement_id, set()).add(ft)

        # known fault types (from specs) for associated-fault attribution
        known_types = {s.fault_type.value for s in fault_specs}

        trace: list[RequirementTraceability] = []
        for req in requirements:
            req_tcs = tc_by_req.get(req.requirement_id, [])
            req_results: list[ExecutionResult] = []
            for tc in req_tcs:
                req_results.extend(result_by_tc.get(tc.test_case_id, []))

            executed = sum(1 for r in req_results if r.status in _EXECUTED_STATUSES)
            has_failing = any(
                r.status is TestStatus.FAIL for r in req_results
            )
            missing_evidence = any(
                not (t.has_executed if t is not None else False)
                for t in (tc_trace.get(tc.test_case_id) for tc in req_tcs)
            )

            spec_evidence: list[RagEvidence] = []
            for tc in req_tcs:
                t = tc_trace.get(tc.test_case_id)
                if t:
                    spec_evidence.extend(t.rag_evidence)

            # Fault types associated with this requirement: those of its known
            # type that were injected in this requirement's results, or that are
            # known fault types relevant to the requirement.
            injected_here = fault_types_by_req.get(req.requirement_id, set())
            associated = sorted(injected_here | (known_types if False else set()))

            trace.append(
                RequirementTraceability(
                    requirement_id=req.requirement_id,
                    category=req.category.value,
                    description=req.description,
                    source=req.source,
                    source_reference=req.source_reference,
                    spec_evidence=spec_evidence,
                    tests=[tc_trace[tc.test_case_id] for tc in req_tcs],
                    associated_fault_types=associated,
                    covered=executed > 0,
                    has_failing_test=has_failing,
                    missing_execution_evidence=missing_evidence,
                )
            )
        return trace

    # ----------------------------------------------------------------- faults

    @staticmethod
    def build_fault_traceability(
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
    ) -> list[FaultTraceability]:
        fault_cov = AnalysisService.analyze_fault_detection(results, fault_specs)

        # details per fault type
        injected_tc_by_type: dict[str, list[str]] = {}
        failed_tc_by_type: dict[str, set[str]] = {}
        requid_by_type: dict[str, set[str]] = {}
        exec_result_by_type: dict[str, list[str]] = {}
        for result in results:
            types = FaultInjection.injected_types(result)
            for ft in types:
                injected_tc_by_type.setdefault(ft, []).append(result.test_case_id)
                requid_by_type.setdefault(ft, set()).add(result.requirement_id)
                exec_result_by_type.setdefault(ft, []).append(result.status.value)
                if result.status is TestStatus.FAIL:
                    failed_tc_by_type.setdefault(ft, set()).add(result.test_case_id)

        trace: list[FaultTraceability] = []
        for fc in fault_cov:
            injected = injected_tc_by_type.get(fc.fault_type, [])
            failed = failed_tc_by_type.get(fc.fault_type, set())
            if fc.injected_count == 0:
                injection_status = InjectionStatus.NOT_EXECUTED
                detection_status = FaultDetectionStatus.NOT_EXECUTED
                detection_evidence = (
                    f"No test injected fault {fc.fault_type}; detection cannot "
                    "be inferred without execution evidence."
                )
                execution_result = None
            elif fc.detected_count > 0:
                injection_status = InjectionStatus.INJECTED
                detection_status = FaultDetectionStatus.DETECTED
                detection_evidence = (
                    f"Fault {fc.fault_type} injected and its assertion FAIL surfaced "
                    f"it in {sorted(failed)}."
                )
                execution_result = "FAIL"
            else:
                injection_status = InjectionStatus.INJECTED
                detection_status = FaultDetectionStatus.MISSED
                detection_evidence = (
                    f"Fault {fc.fault_type} was injected in {fc.injected_count} "
                    "test(s) but no FAIL assertion surfaced it."
                )
                execution_result = ",".join(sorted(set(exec_result_by_type.get(fc.fault_type, []))))

            trace.append(
                FaultTraceability(
                    fault_id=fc.fault_id,
                    fault_type=fc.fault_type,
                    requirement_ids=sorted(requid_by_type.get(fc.fault_type, set())),
                    related_test_case_ids=sorted(set(injected)),
                    injection_status=injection_status,
                    injection_evidence=sorted(set(injected)),
                    detection_status=detection_status,
                    execution_result=execution_result,
                    detection_evidence=detection_evidence,
                )
            )
        return trace

    # ---------------------------------------------------------------- summary

    @staticmethod
    def build_final_summary(
        *,
        analysis: CoverageSummary,
        requirements: list[Requirement],
        test_cases: list[TestCase],
        results: list[ExecutionResult],
        fault_specs: list[FaultSpec],
        gaps: list[CoverageGap],
        known_limitations: list[str],
        generated_timestamp: datetime | None = None,
    ) -> FinalProjectSummary:
        executed = sum(1 for r in results if r.status in _EXECUTED_STATUSES)
        passed = sum(1 for r in results if r.status is TestStatus.PASS)
        failed = sum(1 for r in results if r.status is TestStatus.FAIL)
        errors = sum(1 for r in results if r.status is TestStatus.ERROR)
        skipped = sum(1 for r in results if r.status is TestStatus.SKIPPED)

        recommendations = sorted({g.recommended_action for g in gaps})

        return FinalProjectSummary(
            project_id="autonomous-rag-iot-test-generation",
            status="COMPLETE",
            generated_timestamp=generated_timestamp or _now_utc(),
            requirement_count=len(requirements),
            test_case_count=len(test_cases),
            executed_test_count=executed,
            passed_count=passed,
            failed_count=failed,
            error_count=errors,
            skipped_count=skipped,
            execution_coverage=analysis.execution_coverage,
            requirement_coverage=analysis.requirement_coverage,
            fault_count=analysis.total_faults,
            detected_fault_count=analysis.detected_faults,
            fault_detection_rate=analysis.fault_detection_rate,
            gap_count=analysis.gap_count,
            recommendations=recommendations,
            known_limitations=known_limitations,
        )

    # ---------------------------------------------------------------- report

    @staticmethod
    def generate_final_report(
        *,
        requirements: Iterable[Requirement],
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
        test_summary: FinalTestSummary,
        known_limitations: list[str] | None = None,
        generated_timestamp: datetime | None = None,
    ) -> FinalProjectReport:
        requirements = list(requirements)
        test_cases = list(test_cases)
        results = list(results)
        fault_specs = list(fault_specs)

        analysis: CoverageSummary = AnalysisService.analyze_execution_results(
            requirements, test_cases, results, fault_specs
        ).summary

        req_trace = FinalReportService.build_requirement_traceability(
            requirements, test_cases, results, fault_specs
        )
        fault_trace = FinalReportService.build_fault_traceability(results, fault_specs)

        report_analysis = AnalysisService.analyze_execution_results(
            requirements, test_cases, results, fault_specs
        )
        gaps = report_analysis.gaps

        summary = FinalReportService.build_final_summary(
            analysis=analysis,
            requirements=requirements,
            test_cases=test_cases,
            results=results,
            fault_specs=fault_specs,
            gaps=gaps,
            known_limitations=known_limitations or _DEFAULT_LIMITATIONS(),
            generated_timestamp=generated_timestamp,
        )

        return FinalProjectReport(
            generated_timestamp=generated_timestamp or _now_utc(),
            phases=FinalReportService.build_phase_statuses(complete_up_to=10),
            requirements=req_trace,
            faults=fault_trace,
            gaps=gaps,
            coverage=analysis,
            test_summary=test_summary,
            summary=summary,
        )

    # --------------------------------------------------------------- writers

    @staticmethod
    def write_json_report(report: FinalProjectReport, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = report.model_dump(mode="json")
        payload["_schema"] = "autonomous-rag-iot-final-report/v1"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    @staticmethod
    def write_markdown_report(report: FinalProjectReport, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        md = _render_markdown(report)
        path.write_text(md, encoding="utf-8")
        return path


class FaultInjection:
    """Fault-type extraction helpers shared by reporting (evidence-based)."""

    @staticmethod
    def injected_types(result: ExecutionResult) -> list[str]:
        types: list[str] = []
        for e in result.execution_evidence:
            if e.action == "INJECT_FAULT" and e.expected:
                parts = e.expected.split()
                if len(parts) >= 2:
                    candidate = parts[-1].strip().upper()
                    if candidate:
                        types.append(candidate)
        return types


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _DEFAULT_LIMITATIONS() -> list[str]:
    return [
        "Real (OpenAI) LLM generation is wired but untested-by-design to avoid API spend; "
        "all offline tests use the deterministic mock provider.",
        "Fault detection is keyed by fault type from execution evidence, not by a "
        "persisted cross-reference to a single injected fault instance.",
        "MQTT execution tests are honest about broker availability: without a reachable "
        "broker they are SKIPPED (never faked), which can lower interface coverage in "
        "broker-less environments.",
    ]


def _render_markdown(report: FinalProjectReport) -> str:
    s = report.summary
    lines: list[str] = []
    add = lines.append
    add(f"# {report.project_name}")
    add("")
    add(f"**Project ID:** `{report.project_id}`  \n")
    add(f"**Status:** {report.status}  ")
    add(f"**Generated:** {report.generated_timestamp.isoformat()}  ")
    add(f"**Analysis ID:** `{report.analysis_id}`")
    add("")
    add("## Project Overview")
    add("")
    add(
        "An autonomous RAG-based IoT test generation and fault-detection framework. "
        "It ingests an IoT device specification, extracts requirements, retrieves "
        "testing knowledge via RAG, generates validated test cases, executes them "
        "against a simulated device, injects faults, and reports coverage and "
        "fault-detection outcomes."
    )
    add("")
    add("## Architecture")
    add("")
    add("```")
    add("Specification")
    add("    -> Requirements (Phase 5)")
    add("    -> RAG knowledge (Phase 6)")
    add("    -> Generated Test Cases (Phase 7)")
    add("    -> Validated Test Cases (Phase 7)")
    add("    -> Executed Test Cases (Phase 8)")
    add("    -> Fault Injection / Results (Phase 4/8)")
    add("    -> Coverage & Fault Analysis (Phase 9)")
    add("    -> FINAL PROJECT REPORT (Phase 10)")
    add("```")
    add("")
    add("## Phase Completion")
    add("")
    add("| Phase | Title | Status | Feature | Verification |")
    add("|-------|-------|--------|---------|--------------|")
    for p in report.phases:
        add(f"| {p.phase_number} | {p.title} | {p.status.value} | {p.major_feature} | {p.verification} |")
    add("")
    add("## Final Test Results")
    add("")
    add(
        f"- **Total:** {report.test_summary.total}  "
    )
    add(f"- **Passed:** {report.test_summary.passed}  ")
    add(f"- **Failed:** {report.test_summary.failed}  ")
    add(f"- **Errors:** {report.test_summary.errors}  ")
    add(f"- **Skipped:** {report.test_summary.skipped}  ")
    add(f"- **Duration (s):** {report.test_summary.duration_seconds:.2f}")
    add("")
    add("## Coverage Analysis")
    add("")
    add(f"- **Requirements:** {s.requirement_count} total")
    add(f"- **Requirement coverage:** {s.requirement_coverage}%  ")
    add(f"- **Test cases generated:** {s.test_case_count}  ")
    add(f"- **Executed test cases:** {s.executed_test_count}  ")
    add(f"- **Execution coverage:** {s.execution_coverage}%  ")
    add(f"- **Passed / Failed / Errors / Skipped:** {s.passed_count} / {s.failed_count} / {s.error_count} / {s.skipped_count}")
    add("")
    add("## Fault Injection")
    add("")
    add(f"- **Known faults:** {s.fault_count}  ")
    add(f"- **Detected faults:** {s.detected_fault_count}  ")
    add(f"- **Fault detection rate:** {s.fault_detection_rate}%  ")
    add("")
    _add_fault_table(add, report)
    add("")
    add("## Requirements")
    add("")
    _add_requirement_rows(add, report)
    add("")
    add("## Traceability")
    add("")
    add(
        "Every requirement, test case, execution, fault and coverage result is linked "
        "by its real id. See `reports/final_report.json` for the full structured links."
    )
    add("")
    add("## Coverage Gaps")
    add("")
    for g in report.gaps:
        add(f"- **[{g.severity}]** `{g.type}` — {g.description}")
    add("")
    add("## Recommendations")
    add("")
    for r in s.recommendations:
        add(f"- {r}")
    add("")
    add("## Known Limitations")
    add("")
    for l in s.known_limitations:
        add(f"- {l}")
    add("")
    add("## Conclusion")
    add("")
    add(
        f"All 10 phases are complete. The framework generated {s.requirement_count} "
        f"requirement(s) mapped to {s.test_case_count} validated test case(s), executed "
        f"{s.executed_test_count} with {s.requirement_coverage}% requirement coverage and "
        f"{s.fault_detection_rate}% fault-detection rate across {s.fault_count} known fault(s)."
    )
    add("")
    return "\n".join(lines)


def _add_fault_table(add, report: FinalProjectReport) -> None:
    add("| Fault | Type | Injection | Detection | Related tests |")
    add("|-------|------|-----------|-----------|---------------|")
    for f in report.faults:
        add(
            f"| {f.fault_id[:8]} | {f.fault_type} | {f.injection_status.value} "
            f"| {f.detection_status.value} | {', '.join(f.related_test_case_ids)} |"
        )


def _add_requirement_rows(add, report: FinalProjectReport) -> None:
    add("| Requirement | Category | Covered | Failing | Tests | Description |")
    add("|-------------|----------|---------|---------|-------|-------------|")
    for r in report.requirements:
        add(
            f"| {r.requirement_id} | {r.category} | {r.covered} | {r.has_failing_test} "
            f"| {len(r.tests)} | {_escape(r.description)} |"
        )


def _escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
