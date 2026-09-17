"""
Phase 9 — Coverage & Fault Analysis service.

WHY:
    A clean, deterministic entry point that consumes ONLY trusted structured
    artifacts produced by earlier phases — Phase 5 `Requirement`s, Phase 7
    `TestCase`s, Phase 8 `ExecutionResult`s and Phase 4 `FaultSpec`s — and
    turns them into an `AnalysisReport`. Phase 9 never generates new tests,
    never executes anything, and never mutates results to boost coverage.

WHAT:
    - analyze_requirement_coverage(...)  -> list[RequirementCoverage]
    - analyze_test_coverage(...)         -> TestCoverage (overall + by category)
    - analyze_interface_coverage(...)    -> list[InterfaceCoverage]
    - analyze_fault_detection(...)       -> list[FaultCoverage]
    - identify_gaps(...)                 -> list[CoverageGap]
    - generate_summary(...)              -> CoverageSummary
    - analyze_execution_results(...)     -> AnalysisReport (orchestrator)

HOW (rules — see models.py for the full contract):
    - EXECUTED  := result.status in {PASS, FAIL}; both genuinely exercised the
      device. ERROR and SKIPPED never count as executed coverage.
    - PASS rate := passed / total * 100 (matches Phase 8 ExecutionSummary).
    - Execution coverage := executed / total * 100.
    - A requirement is covered iff >=1 of its tests executed (PASS/FAIL).
    - A fault type is DETECTED only if a test that INJECTED it ended FAIL
      (its assertion actually surfaced the injected fault). Injecting a fault
      with no failing assertion is injected-but-missed, never assumed detected.
    - Interfaces are NEVER invented: they are derived from each TestCase's
      `protocol` metadata (SENSOR -> "Sensor/simulator", MQTT -> "MQTT", ...).
    - Nonexistent requirements/faults are ignored; zero denominators yield 0%.

HOW TO VERIFY:
    See tests/unit/test_analysis_*.py and
    tests/integration/test_analysis_full_chain.py.
"""

from __future__ import annotations

from typing import Iterable

from app.analysis.models import (
    AnalysisReport,
    CategoryTestCoverage,
    CoverageGap,
    CoverageSummary,
    FaultCoverage,
    GapType,
    InterfaceCoverage,
    RequirementCoverage,
    TestCoverage,
)
from app.faults.models import FaultSpec
from app.ingestion.models import Requirement
from app.llm.models import TestCase
from app.testing.models import ExecutionResult, TestStatus

# Values that genuinely execute a test against the device.
_EXECUTED_STATUSES = frozenset({TestStatus.PASS, TestStatus.FAIL})

# Interface label for a protocol; unknown protocols keep their own value.
_INTERFACE_LABELS = {
    "SENSOR": "Sensor/simulator",
    "MQTT": "MQTT",
}

# Numeric/range-style requirement categories for which BOUNDARY/NEGATIVE
# coverage is meaningful (matches the Phase 7 mock generator's context).
_BOUNDARY_CATEGORIES = frozenset({"RANGE", "ACCURACY"})


def _pct(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _executed_count(results: Iterable[ExecutionResult]) -> int:
    return sum(1 for r in results if r.status in _EXECUTED_STATUSES)


class AnalysisService:
    """Deterministic coverage & fault-detection analysis over trusted data."""

    # ------------------------------------------------------------------ parts

    @staticmethod
    def analyze_requirement_coverage(
        requirements: Iterable[Requirement],
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
    ) -> list[RequirementCoverage]:
        """Per-requirement coverage. Coverage requires an executed (PASS/FAIL)
        result for at least one of the requirement's tests."""
        tc_by_req: dict[str, list[TestCase]] = {}
        for tc in test_cases:
            tc_by_req.setdefault(tc.requirement_id, []).append(tc)

        result_by_tc: dict[str, list[ExecutionResult]] = {}
        for result in results:
            result_by_tc.setdefault(result.test_case_id, []).append(result)

        coverages: list[RequirementCoverage] = []
        for req in requirements:
            req_tcs = tc_by_req.get(req.requirement_id, [])
            req_results: list[ExecutionResult] = []
            for tc in req_tcs:
                req_results.extend(result_by_tc.get(tc.test_case_id, []))

            executed = sum(1 for r in req_results if r.status in _EXECUTED_STATUSES)
            passed = sum(1 for r in req_results if r.status is TestStatus.PASS)
            failed = sum(1 for r in req_results if r.status is TestStatus.FAIL)
            errors = sum(1 for r in req_results if r.status is TestStatus.ERROR)
            skipped = sum(1 for r in req_results if r.status is TestStatus.SKIPPED)

            coverages.append(
                RequirementCoverage(
                    requirement_id=req.requirement_id,
                    category=req.category.value,
                    total_generated=len(req_tcs),
                    executed=executed,
                    passed=passed,
                    failed=failed,
                    errors=errors,
                    skipped=skipped,
                    covered=executed > 0,
                )
            )
        return coverages

    @staticmethod
    def analyze_test_coverage(
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
    ) -> TestCoverage:
        """Overall + per-category executed-test statistics."""
        tc_by_id: dict[str, tuple[str, str]] = {
            tc.test_case_id: (tc.category.value, tc.protocol or "SENSOR")
            for tc in test_cases
        }
        # category -> {'total':n,'executed':n,...}
        per_category: dict[str, dict] = {}
        for tc in test_cases:
            cat = tc.category.value
            bucket = per_category.setdefault(
                cat, {"total": 0, "executed": 0, "passed": 0, "failed": 0,
                      "errors": 0, "skipped": 0}
            )
            bucket["total"] += 1

        total = len(test_cases)
        executed = passed = failed = errors = skipped = 0
        for result in results:
            cat = tc_by_id.get(result.test_case_id, ("UNKNOWN", "UNKNOWN"))[0]
            bucket = per_category.setdefault(
                cat, {"total": 0, "executed": 0, "passed": 0, "failed": 0,
                      "errors": 0, "skipped": 0}
            )
            if result.status is TestStatus.PASS:
                executed += 1; passed += 1
                bucket["executed"] += 1; bucket["passed"] += 1
            elif result.status is TestStatus.FAIL:
                executed += 1; failed += 1
                bucket["executed"] += 1; bucket["failed"] += 1
            elif result.status is TestStatus.ERROR:
                errors += 1; bucket["errors"] += 1
            else:  # SKIPPED
                skipped += 1; bucket["skipped"] += 1

        by_category = [
            CategoryTestCoverage(
                category=cat,
                total=b["total"],
                executed=b["executed"],
                passed=b["passed"],
                failed=b["failed"],
                errors=b["errors"],
                skipped=b["skipped"],
                execution_coverage=_pct(b["executed"], b["total"]),
                pass_rate=_pct(b["passed"], b["total"]),
            )
            for cat, b in sorted(per_category.items())
        ]

        return TestCoverage(
            total=total,
            executed=executed,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            execution_coverage=_pct(executed, total),
            pass_rate=_pct(passed, total),
            by_category=by_category,
        )

    @staticmethod
    def analyze_interface_coverage(
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
    ) -> list[InterfaceCoverage]:
        """Per-interface coverage, derived ONLY from existing TestCase protocol
        metadata (never invented). An interface is covered when at least one of
        its tests actually executed (PASS/FAIL)."""
        tc_protocol_by_id: dict[str, str] = {}
        protocol_totals: dict[str, int] = {}
        for tc in test_cases:
            proto = (tc.protocol or "SENSOR").upper()
            tc_protocol_by_id[tc.test_case_id] = proto
            protocol_totals[proto] = protocol_totals.get(proto, 0) + 1

        counts: dict[str, dict] = {}
        for result in results:
            proto = tc_protocol_by_id.get(result.test_case_id)
            if proto is None:
                continue
            bucket = counts.setdefault(
                proto, {"executed": 0, "passed": 0, "failed": 0,
                        "errors": 0, "skipped": 0}
            )
            if result.status is TestStatus.PASS:
                bucket["executed"] += 1; bucket["passed"] += 1
            elif result.status is TestStatus.FAIL:
                bucket["executed"] += 1; bucket["failed"] += 1
            elif result.status is TestStatus.ERROR:
                bucket["errors"] += 1
            else:
                bucket["skipped"] += 1

        coverages: list[InterfaceCoverage] = []
        for proto in sorted(protocol_totals):
            b = counts.get(proto, {})
            executed = b.get("executed", 0)
            coverages.append(
                InterfaceCoverage(
                    interface=_INTERFACE_LABELS.get(proto, proto),
                    protocol=proto,
                    total=protocol_totals[proto],
                    executed=executed,
                    passed=b.get("passed", 0),
                    failed=b.get("failed", 0),
                    errors=b.get("errors", 0),
                    skipped=b.get("skipped", 0),
                    covered=executed > 0,
                )
            )
        return coverages

    @staticmethod
    def analyze_fault_detection(
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
    ) -> list[FaultCoverage]:
        """Per-known-fault-type detection from real execution evidence.

        For each distinct FaultType among the supplied `fault_specs`, gather
        every ExecutionResult whose evidence performed an INJECT_FAULT action
        of that type. A fault is DETECTED when such a test ended FAIL — i.e.
        its assertion genuinely surfaced the injected fault. A FAIL-free
        injection (test passed but no assertion caught it) counts as missed.
        """
        known_types: dict[str, FaultSpec] = {}
        for spec in fault_specs:
            known_types.setdefault(spec.fault_type.value, spec)

        injected_by_type: dict[str, list[str]] = {}
        failed_by_type: dict[str, set[str]] = {}
        for result in results:
            fault_types = _injected_fault_types(result)
            for ft in fault_types:
                injected_by_type.setdefault(ft, []).append(result.test_case_id)
                if result.status is TestStatus.FAIL:
                    failed_by_type.setdefault(ft, set()).add(result.test_case_id)

        coverages: list[FaultCoverage] = []
        for ft, spec in sorted(known_types.items()):
            injected = injected_by_type.get(ft, [])
            detected_tcs = failed_by_type.get(ft, set())
            detected_count = len(detected_tcs)
            coverages.append(
                FaultCoverage(
                    fault_id=spec.fault_id,
                    fault_type=ft,
                    detected=detected_count > 0,
                    injected_count=len(injected),
                    detected_count=detected_count,
                    missed_count=max(0, len(injected) - detected_count),
                    detection_rate=_pct(detected_count, len(injected)),
                    related_test_cases=sorted(set(injected)),
                )
            )
        return coverages

    # ------------------------------------------------------------------ gaps

    @staticmethod
    def identify_gaps(
        requirements: Iterable[Requirement],
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
    ) -> list[CoverageGap]:
        """Identify structured, meaningful gaps. Phase 9 NEVER fills them."""
        reqs = list(requirements)
        tcs = list(test_cases)
        res = list(results)
        fault_specs = list(fault_specs)

        tc_by_id = {tc.test_case_id: tc for tc in tcs}
        result_ids = {r.test_case_id for r in res}
        executed_ids = {r.test_case_id for r in res if r.status in _EXECUTED_STATUSES}

        gaps: list[CoverageGap] = []
        gap_index = 0

        def _add(gtype: GapType, *, requirement_id=None, related_test_case_id=None,
                 description: str, severity: str, recommended_action: str) -> None:
            nonlocal gap_index
            gap_index += 1
            gaps.append(
                CoverageGap(
                    gap_id=f"GAP-{gap_index:03d}",
                    type=gtype,
                    requirement_id=requirement_id,
                    related_test_case_id=related_test_case_id,
                    description=description,
                    severity=severity,  # type: ignore[arg-type]
                    recommended_action=recommended_action,
                )
            )

        # 1) Test generated but never executed.
        for tc in tcs:
            if tc.test_case_id not in result_ids:
                _add(
                    "TEST_GENERATED_NOT_EXECUTED",
                    requirement_id=tc.requirement_id,
                    related_test_case_id=tc.test_case_id,
                    description=(
                        f"Test {tc.test_case_id} ({tc.category.value}) was generated "
                        f"for requirement {tc.requirement_id} but never executed."
                    ),
                    severity="HIGH",
                    recommended_action="Execute the test to confirm the behavior it targets.",
                )

        # 2) Skipped executions.
        for r in res:
            if r.status is TestStatus.SKIPPED:
                _add(
                    "TEST_SKIPPED",
                    requirement_id=r.requirement_id,
                    related_test_case_id=r.test_case_id,
                    description=(
                        f"Test {r.test_case_id} was skipped: "
                        f"{r.failure_reason or 'a step was skipped'}."
                    ),
                    severity="MEDIUM",
                    recommended_action="Ensure the required environment (e.g. MQTT broker) is available and re-run.",
                )

        # 3) Requirement-level coverage + category gaps.
        per_req_tcs: dict[str, list[TestCase]] = {}
        for tc in tcs:
            per_req_tcs.setdefault(tc.requirement_id, []).append(tc)

        for req in reqs:
            req_tcs = per_req_tcs.get(req.requirement_id, [])
            executed_cats: set[str] = {
                tc_by_id[tc.test_case_id].category.value
                for tc in req_tcs
                if tc.test_case_id in executed_ids
            }
            all_cats: set[str] = {tc.category.value for tc in req_tcs}
            if req_tcs and not any(tc.test_case_id in executed_ids for tc in req_tcs):
                _add(
                    "REQUIREMENT_NO_EXECUTED_TEST",
                    requirement_id=req.requirement_id,
                    description=(
                        f"Requirement {req.requirement_id} has no executed test "
                        f"(no result with PASS/FAIL)."
                    ),
                    severity="HIGH",
                    recommended_action="Execute at least one test for this requirement.",
                )
            if req.category.value in _BOUNDARY_CATEGORIES and req_tcs:
                if not executed_cats and all_cats and not executed_ids:
                    pass  # no-exec gap already reported above
                if executed_cats and "BOUNDARY" not in executed_cats:
                    _add(
                        "BOUNDARY_MISSING",
                        requirement_id=req.requirement_id,
                        description=(
                            f"Requirement {req.requirement_id} has executed tests but none "
                            "at a boundary value."
                        ),
                        severity="MEDIUM",
                        recommended_action="Add and execute a BOUNDARY test for the declared range.",
                    )
                if executed_cats and "NEGATIVE" not in executed_cats:
                    _add(
                        "NEGATIVE_MISSING",
                        requirement_id=req.requirement_id,
                        description=(
                            f"Requirement {req.requirement_id} has executed tests but no "
                            "NEGATIVE (out-of-range) test."
                        ),
                        severity="MEDIUM",
                        recommended_action="Add and execute a NEGATIVE test for the declared range.",
                    )
                if all_cats and executed_cats and all_cats == {"POSITIVE"}:
                    _add(
                        "REQUIREMENT_ONLY_POSITIVE",
                        requirement_id=req.requirement_id,
                        description=(
                            f"Requirement {req.requirement_id} is covered only by POSITIVE "
                            "tests; no boundary/negative paths exercised."
                        ),
                        severity="MEDIUM",
                        recommended_action="Add boundary and negative tests for this requirement.",
                    )

        # 4) Interface / protocol coverage gaps.
        interface_cov = AnalysisService.analyze_interface_coverage(tcs, res)
        for ic in interface_cov:
            if ic.executed == 0 and ic.total > 0:
                _add(
                    "INTERFACE_NO_EXECUTED_TEST",
                    description=(
                        f"Interface '{ic.interface}' has {ic.total} test(s) but none "
                        "actually executed (all skipped/errored or none run)."
                    ),
                    severity="HIGH",
                    recommended_action="Provide the interface's runtime (e.g. MQTT broker) and execute its tests.",
                )

        # 5) Fault gaps.
        fault_cov = AnalysisService.analyze_fault_detection(res, fault_specs)
        for fc in fault_cov:
            if fc.injected_count == 0:
                _add(
                    "FAULT_NO_TEST",
                    description=(
                        f"Fault {fc.fault_type} is a known fault but no test injected it."
                    ),
                    severity="HIGH",
                    recommended_action=(
                        f"Add and execute a test that injects fault {fc.fault_type}."
                    ),
                )
            elif fc.detected_count == 0:
                _add(
                    "FAULT_NOT_DETECTED",
                    description=(
                        f"Fault {fc.fault_type} was injected in "
                        f"{fc.injected_count} test(s) but DETECTED in none (no FAIL "
                        "assertion surfaced it)."
                    ),
                    severity="HIGH",
                    recommended_action=(
                        f"Add an assertion that evaluates the faulted behavior so fault "
                        f"{fc.fault_type} is detected."
                    ),
                )

        return gaps

    # ------------------------------------------------------------------ summary

    @staticmethod
    def generate_summary(
        requirement_coverage: Iterable[RequirementCoverage],
        test_coverage: TestCoverage,
        fault_coverage: Iterable[FaultCoverage],
        gap_count: int,
    ) -> CoverageSummary:
        reqs = list(requirement_coverage)
        faults = list(fault_coverage)
        total_requirements = len(reqs)
        covered_requirements = sum(1 for rc in reqs if rc.covered)
        total_faults = len(faults)
        detected_faults = sum(1 for fc in faults if fc.detected)
        total_injected = sum(fc.injected_count for fc in faults)
        total_detected = sum(fc.detected_count for fc in faults)
        return CoverageSummary(
            total_requirements=total_requirements,
            covered_requirements=covered_requirements,
            requirement_coverage=_pct(covered_requirements, total_requirements),
            total_test_cases=test_coverage.total,
            executed_test_cases=test_coverage.executed,
            execution_coverage=test_coverage.execution_coverage,
            pass_rate=test_coverage.pass_rate,
            total_faults=total_faults,
            detected_faults=detected_faults,
            fault_detection_rate=_pct(total_detected, total_injected),
            gap_count=gap_count,
        )

    # ------------------------------------------------------------------ report

    @staticmethod
    def analyze_execution_results(
        requirements: Iterable[Requirement],
        test_cases: Iterable[TestCase],
        results: Iterable[ExecutionResult],
        fault_specs: Iterable[FaultSpec],
    ) -> AnalysisReport:
        """Full Phase 9 orchestration: coverage + faults + gaps + summary."""
        req_cov = AnalysisService.analyze_requirement_coverage(
            requirements, test_cases, results
        )
        test_cov = AnalysisService.analyze_test_coverage(test_cases, results)
        interface_cov = AnalysisService.analyze_interface_coverage(test_cases, results)
        fault_cov = AnalysisService.analyze_fault_detection(results, fault_specs)
        gaps = AnalysisService.identify_gaps(
            requirements, test_cases, results, fault_specs
        )
        summary = AnalysisService.generate_summary(
            req_cov, test_cov, fault_cov, len(gaps)
        )
        recommendations = _recommendations(gaps)

        return AnalysisReport(
            summary=summary,
            requirement_coverage=req_cov,
            test_coverage=test_cov,
            interface_coverage=interface_cov,
            fault_coverage=fault_cov,
            gaps=gaps,
            recommendations=recommendations,
        )


def _injected_fault_types(result: ExecutionResult) -> list[str]:
    """Fault types this execution injected (from INJECT_FAULT evidence).

    The executor records each INJECT_FAULT step's `expected` as
    "inject <FaultType>" (e.g. "inject SENSOR_OUT_OF_RANGE"), so the
    canonical FaultType token is the last whitespace token, uppercased to
    match `FaultType.value`.
    """
    out: list[str] = []
    for e in result.execution_evidence:
        if e.action == "INJECT_FAULT" and e.expected:
            parts = e.expected.split()
            if len(parts) >= 2:
                candidate = parts[-1].strip().upper()
                if candidate:
                    out.append(candidate)
    return out


def _recommendations(gaps: Iterable[CoverageGap]) -> list[str]:
    """Human, deduplicated recommendation strings derived from gaps only."""
    seen: set[str] = set()
    out: list[str] = []
    for gap in gaps:
        text = gap.recommended_action
        key = text.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(text)
    return out
