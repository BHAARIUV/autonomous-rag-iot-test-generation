"""
Phase 11 — Autonomous Test-Refinement Loop service.

WHY:
    The initial suite (Phase 7) + execution (Phase 8) + analysis (Phase 9)
    often leaves gaps. This loop AUTOMATICALLY:

        execute results -> analysis -> select gap -> (requirement-aware RAG)
        -> generate -> validate -> execute -> re-analyse -> compare before/after
        -> repeat until a stop condition.

WHAT:
    `RefinementService.run(...)` drives the loop over a working set of test
    cases and execution results, reusing ONLY existing, tested components:
      - app.analysis.AnalysisService      (gap + coverage analysis, Phase 9)
      - app.llm.service.GenerationService (RAG-aware generation + validation, Phase 6/7)
      - app.testing.ExecutionService      (safe, closed-action execution, Phase 8)
      - app.config.Settings               (limits: max_iterations, target coverage)

HOW (rules — see models.py):
    - Only VALIDATED TestCase objects ever enter execution (Phase 7 guarantee).
    - Execution uses the safe Phase 8 executor / closed action set. No eval/exec,
      no running generated code.
    - Every gap comes from REAL Phase 9 analysis — never invented.
    - Before/After snapshots and improvement are measured from real analysis.
    - The loop ALWAYS terminates with an explicit, recorded StopReason.
    - Deduplication: tests with identical content are not added twice.
    - MQTT-dependent and fault-generation gaps are honestly marked not
      addressable by re-generation and do NOT block progress on other gaps.

HOW TO VERIFY:
    See tests/unit/test_refinement_*.py and
    tests/integration/test_refinement_full_chain.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from loguru import logger

from app.analysis import AnalysisService
from app.config import Settings, settings as _default_settings
from app.faults.models import FaultSpec
from app.ingestion.models import Requirement
from app.llm.models import TestCase
from app.llm.service import GenerationService
from app.refinement.models import (
    CoverageSnapshot,
    RefinementDecision,
    RefinementGap,
    RefinementIteration,
    RefinementResult,
    StopReason,
)
from app.testing import ExecutionService
from app.testing.models import ExecutionResult, TestStatus

# Map a Phase 9 gap type to the refinement action we can honestly take.
_GAP_DECISIONS: dict[str, RefinementDecision] = {
    "TEST_GENERATED_NOT_EXECUTED": RefinementDecision.EXECUTE_EXISTING,
    "REQUIREMENT_NO_EXECUTED_TEST": RefinementDecision.REGENERATE,
    "REQUIREMENT_ONLY_POSITIVE": RefinementDecision.REGENERATE,
    "BOUNDARY_MISSING": RefinementDecision.REGENERATE,
    "NEGATIVE_MISSING": RefinementDecision.REGENERATE,
    "FAULT_NO_TEST": RefinementDecision.NOT_ADDRESSABLE,
    "FAULT_NOT_DETECTED": RefinementDecision.NOT_ADDRESSABLE,
    "INTERFACE_NO_EXECUTED_TEST": RefinementDecision.SKIP_ENVIRONMENT,
    "TEST_SKIPPED": RefinementDecision.SKIP_ENVIRONMENT,
}

_ADDRESSABLE_DECISIONS = {
    RefinementDecision.REGENERATE,
    RefinementDecision.EXECUTE_EXISTING,
}

_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _content_key(tc: TestCase) -> tuple:
    """Deduplication signature: identical content => same key, regardless of id."""
    steps = tuple((s.step_number, s.action) for s in tc.test_steps)
    return (tc.requirement_id, tc.category.value, steps, tc.expected_result)


def _requirement_query(requirement: Requirement, gap: RefinementGap | None) -> str:
    """Requirement-aware, gap-enriched query used for retrieval evidence."""
    base = f"{requirement.requirement_id}: {requirement.description}"
    if gap is not None:
        base += f" [gap={gap.gap_type}]"
    return base


def _delta(before: float, after: float) -> float:
    return round(max(0.0, after - before), 2)


class RefinementService:
    """Drives the autonomous refinement loop over real Phase 5-9 artifacts."""

    def __init__(
        self,
        *,
        settings_: Settings | None = None,
        generator: GenerationService | None = None,
        executor: ExecutionService | None = None,
        max_iterations: int | None = None,
        min_improvement: float | None = None,
        target_requirement_coverage: float | None = None,
    ):
        self._settings = settings_ if settings_ is not None else _default_settings
        self._generator = generator
        self._executor = executor
        self._max_iterations = (
            max_iterations if max_iterations is not None
            else self._settings.max_refinement_iterations
        )
        self._min_improvement = (
            min_improvement if min_improvement is not None else 0.0
        )
        self._target_coverage = (
            target_requirement_coverage
            if target_requirement_coverage is not None
            else self._settings.target_requirement_coverage
        )

    # ------------------------------------------------------------------ API

    def run(
        self,
        *,
        requirements: Iterable[Requirement],
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
    ) -> RefinementResult:
        """Run the refinement loop and return a fully-traceable result."""
        req_by_id = {r.requirement_id: r for r in requirements}
        fault_specs = list(fault_specs)
        working_tcs = {tc.test_case_id: tc for tc in test_cases}
        working_results = {r.execution_id: r for r in results}
        content_seen = {_content_key(tc): tc.test_case_id for tc in working_tcs.values()}

        started = _now_utc()
        iterations: list[RefinementIteration] = []
        total_generated = 0
        total_executed = 0

        initial = self._snapshot(req_by_id, working_tcs, working_results, fault_specs)

        attempted_gap_ids: set[str] = set()
        consecutive_no_progress = 0
        stop_reason: StopReason | None = None
        stop_detail = ""

        for iteration_no in range(1, self._max_iterations + 1):
            before = self._snapshot(req_by_id, working_tcs, working_results, fault_specs)
            report = AnalysisService.analyze_execution_results(
                req_by_id.values(), working_tcs.values(),
                working_results.values(), fault_specs,
            )
            gaps = self._rank_gaps(
                list(report.gaps) + self._augment_uncovered_gaps(report, req_by_id),
                attempted_gap_ids,
            )

            if not gaps:
                stop_reason = StopReason.NO_GAPS
                stop_detail = "No remaining gaps to act on."
                break

            if before.requirement_coverage >= self._target_coverage:
                stop_reason = StopReason.TARGET_REACHED
                stop_detail = (
                    f"Requirement coverage {before.requirement_coverage}% "
                    f">= target {self._target_coverage}%."
                )
                break

            selected = gaps[0]
            attempted_gap_ids.add(selected.gap_id)
            decision = selected.decision

            if decision is RefinementDecision.REGENERATE:
                iteration, new_tcs, new_results, generated, executed = self._act_regenerate(
                    selected, iteration_no, req_by_id, working_tcs,
                    working_results, content_seen, fault_specs,
                )
            elif decision is RefinementDecision.EXECUTE_EXISTING:
                iteration, new_tcs, new_results, generated, executed = self._act_execute_existing(
                    selected, iteration_no, req_by_id, working_tcs,
                    working_results, fault_specs,
                )
            else:
                iteration, new_tcs, new_results, generated, executed = (
                    self._act_noop(selected, iteration_no, before)
                )

            for tc in new_tcs:
                content_seen.setdefault(_content_key(tc), tc.test_case_id)
                working_tcs[tc.test_case_id] = tc
            for res in new_results:
                working_results[res.execution_id] = res
            total_generated += generated
            total_executed += executed

            iterations.append(iteration)
            after = iteration.coverage_after

            if after.requirement_coverage >= self._target_coverage:
                stop_reason = StopReason.TARGET_REACHED
                stop_detail = (
                    f"Requirement coverage reached {after.requirement_coverage}% "
                    f">= target {self._target_coverage}%."
                )
                break

            made_new_work = generated > 0 or executed > 0
            if iteration.improvement > self._min_improvement or made_new_work:
                consecutive_no_progress = 0
            else:
                consecutive_no_progress += 1
                if consecutive_no_progress >= 2:
                    stop_reason = StopReason.NO_IMPROVEMENT
                    stop_detail = (
                        "Two consecutive iterations produced no measured improvement "
                        "and no new generated/executed tests."
                    )
                    break
        else:
            stop_reason = StopReason.MAX_ITERATIONS
            stop_detail = f"Reached maximum refinement iterations ({self._max_iterations})."

        if stop_reason is None:  # pragma: no cover - defensive
            stop_reason = StopReason.MAX_ITERATIONS
            stop_detail = f"Reached maximum refinement iterations ({self._max_iterations})."

        final = self._snapshot(req_by_id, working_tcs, working_results, fault_specs)
        result = RefinementResult(
            started_timestamp=started,
            finished_timestamp=_now_utc(),
            initial_coverage=initial,
            final_coverage=final,
            final_gap_count=final.gap_count,
            improvement_requirement_coverage=_delta(
                initial.requirement_coverage, final.requirement_coverage
            ),
            improvement_execution_coverage=_delta(
                initial.execution_coverage, final.execution_coverage
            ),
            improvement_fault_detection=_delta(
                initial.fault_detection_rate, final.fault_detection_rate
            ),
            iterations=iterations,
            stop_reason=stop_reason,
            stop_detail=stop_detail,
            total_generated=total_generated,
            total_executed=total_executed,
            final_test_case_ids=sorted(working_tcs),
            final_result_ids=sorted(working_results),
        )
        logger.info(
            f"Refinement {result.refinement_id}: {stop_reason.value} after "
            f"{len(iterations)} iteration(s); req coverage "
            f"{initial.requirement_coverage}% -> {final.requirement_coverage}%."
        )
        return result

    # --------------------------------------------------------------- actions

    def _act_regenerate(self, gap, iteration_no, req_by_id, working_tcs,
                        working_results, content_seen, fault_specs):
        requirement = req_by_id.get(gap.requirement_id or "")
        before = self._snapshot(req_by_id, working_tcs, working_results, fault_specs)
        if requirement is None or self._generator is None or self._executor is None:
            return self._noop_iter(
                gap, iteration_no, before,
                "Cannot regenerate: no requirement / generator / executor available.",
                RefinementDecision.SKIP_ENVIRONMENT,
            )

        query = _requirement_query(requirement, gap)
        suite = self._generator.generate_for_requirement(
            requirement, top_k=self._settings.rag_top_k
        )
        evidence = self._evidence_chunk_ids(suite)

        new_tcs: list[TestCase] = []
        duplicates = 0
        for tc in suite.test_cases:
            if _content_key(tc) in content_seen:
                duplicates += 1
                continue
            new_tcs.append(
                tc.model_copy(update={"test_case_id": f"TC-R{iteration_no:02d}-{len(new_tcs) + 1:03d}"})
            )

        if not new_tcs:
            validation_outcome = "NONE" if duplicates == len(suite.test_cases) else "FAILED"
            iteration = RefinementIteration(
                iteration_number=iteration_no,
                selected_gap=gap,
                decision=RefinementDecision.REGENERATE,
                retrieved_evidence=evidence,
                validation_outcome=validation_outcome,
                coverage_before=before,
                coverage_after=before,
                improvement=0.0,
                attempted_gap_ids={gap.gap_id},
                note=(query if gap.requirement_id else "") + " [all duplicates; no new tests]",
            )
            return iteration, [], [], 0, 0

        execution_outcome = "NONE"
        new_results: list[ExecutionResult] = []
        executed = 0
        try:
            results, _ = self._executor.execute_test_cases(new_tcs)
            new_results = list(results)
            executed = sum(1 for r in new_results if r.status in (TestStatus.PASS, TestStatus.FAIL))
            execution_outcome = "EXECUTED"
        except Exception:
            execution_outcome = "ERROR"

        # Commit the new tests/results temporarily to measure AFTER honestly.
        tcs2 = dict(working_tcs)
        for tc in new_tcs:
            tcs2[tc.test_case_id] = tc
        res2 = dict(working_results)
        for r in new_results:
            res2[r.execution_id] = r
        after = self._snapshot(req_by_id, tcs2, res2, fault_specs)
        improvement = round(after.requirement_coverage - before.requirement_coverage, 2)

        iteration = RefinementIteration(
            iteration_number=iteration_no,
            selected_gap=gap,
            decision=RefinementDecision.REGENERATE,
            retrieved_evidence=evidence,
            generated_test_case_ids=[tc.test_case_id for tc in new_tcs],
            validation_outcome="VALIDATED",
            executed_ids=[r.test_case_id for r in new_results],
            execution_outcome=execution_outcome,
            coverage_before=before,
            coverage_after=after,
            improvement=improvement,
            attempted_gap_ids={gap.gap_id},
            note=query if gap.requirement_id else "",
        )
        return iteration, new_tcs, new_results, len(new_tcs), executed

    def _act_execute_existing(self, gap, iteration_no, req_by_id, working_tcs,
                              working_results, fault_specs):
        before = self._snapshot(req_by_id, working_tcs, working_results, fault_specs)
        tc_id = gap.related_test_case_id
        tc = working_tcs.get(tc_id) if tc_id else None
        if tc is None or self._executor is None:
            return self._noop_iter(
                gap, iteration_no, before,
                "Related generated test is unavailable to execute.",
                RefinementDecision.NOT_ADDRESSABLE,
            )
        try:
            result = self._executor.execute_test_case(tc)
        except Exception:
            result = None
        new_results = [result] if result is not None else []
        executed = bool(
            result is not None and result.status in (TestStatus.PASS, TestStatus.FAIL)
        )
        res2 = dict(working_results)
        for r in new_results:
            res2[r.execution_id] = r
        after = self._snapshot(req_by_id, working_tcs, res2, fault_specs)
        improvement = round(after.requirement_coverage - before.requirement_coverage, 2)
        iteration = RefinementIteration(
            iteration_number=iteration_no,
            selected_gap=gap,
            decision=RefinementDecision.EXECUTE_EXISTING,
            executed_ids=[tc_id] if result is not None else [],
            execution_outcome=("EXECUTED" if result is not None else "ERROR"),
            coverage_before=before,
            coverage_after=after,
            improvement=improvement,
            attempted_gap_ids={gap.gap_id},
            note=f"Executed previously-generated test {tc_id}.",
        )
        return iteration, [], new_results, 0, (1 if executed else 0)

    def _act_noop(self, gap, iteration_no, before):
        return self._noop_iter(
            gap, iteration_no, before,
            "not addressable by safe re-generation" if gap.decision is RefinementDecision.NOT_ADDRESSABLE
            else "requires environment not currently available (e.g. MQTT)",
            gap.decision,
        )

    def _noop_iter(self, gap, iteration_no, before, note, decision):
        iteration = RefinementIteration(
            iteration_number=iteration_no,
            selected_gap=gap,
            decision=decision,
            coverage_before=before,
            coverage_after=before,
            improvement=0.0,
            attempted_gap_ids={gap.gap_id},
            note=note,
        )
        return iteration, [], [], 0, 0

    # --------------------------------------------------------------- helpers

    def _snapshot(self, req_by_id, tcs_by_id, results_by_id, fault_specs) -> CoverageSnapshot:
        report = AnalysisService.analyze_execution_results(
            req_by_id.values(), tcs_by_id.values(), results_by_id.values(), fault_specs
        )
        return CoverageSnapshot.from_summary(report.summary)

    @staticmethod
    def _evidence_chunk_ids(suite) -> list[str]:
        if not suite.test_cases:
            return []
        context = suite.test_cases[0].source_context
        if context is None:
            return []
        return [c.chunk_id for c in context.chunks]

    @staticmethod
    def _augment_uncovered_gaps(report, req_by_id) -> list[RefinementGap]:
        """Yield a REQUIREMENT_NO_EXECUTED_TEST gap for every requirement the
        real Phase 9 analysis marks as uncovered and that has no existing gap.

        Derived entirely from `report.requirement_coverage` (a requirement exists
        and is NOT covered) — it is not an invented gap. This lets the loop act on
        requirements that have no generated tests yet (which Phase 9 itself does
        not flag, because those requirements have no tests to report)."""
        out: list[RefinementGap] = []
        referenced = {g.requirement_id for g in report.gaps if g.requirement_id}
        for rc in report.requirement_coverage:
            if rc.covered or rc.requirement_id in referenced:
                continue
            if rc.requirement_id not in req_by_id:
                continue
            out.append(
                RefinementGap(
                    gap_id=f"REQ-GAP-{rc.requirement_id}",
                    gap_type="REQUIREMENT_NO_EXECUTED_TEST",
                    requirement_id=rc.requirement_id,
                    related_test_case_id=None,
                    description=(
                        f"Requirement {rc.requirement_id} is completely uncovered "
                        f"(no generated tests yet)."
                    ),
                    severity="HIGH",
                    recommended_action=(
                        f"Generate and execute at least one test for requirement "
                        f"{rc.requirement_id}."
                    ),
                    decision=RefinementDecision.REGENERATE,
                )
            )
        return out

    @staticmethod
    def _rank_gaps(gaps, attempted) -> list[RefinementGap]:
        ranked: list[RefinementGap] = []
        for g in gaps:
            if isinstance(g, RefinementGap):
                ranked.append(g)
            else:
                decision = _GAP_DECISIONS.get(getattr(g, "type", ""), RefinementDecision.NOT_ADDRESSABLE)
                if getattr(g, "gap_id", "") in attempted and decision in _ADDRESSABLE_DECISIONS:
                    continue  # already acted on this exact addressable gap
                ranked.append(
                    RefinementGap(
                        gap_id=g.gap_id,
                        gap_type=g.type,
                        requirement_id=g.requirement_id,
                        related_test_case_id=g.related_test_case_id,
                        description=g.description,
                        severity=getattr(g, "severity", "LOW"),
                        recommended_action=g.recommended_action,
                        decision=decision,
                    )
                )
        ranked.sort(key=lambda rg: (
            0 if rg.decision in _ADDRESSABLE_DECISIONS else 1,
            _SEVERITY_ORDER.get(rg.severity, 4),
            rg.gap_id,
        ))
        return ranked


__all__ = ["RefinementService"]
