"""
Phase 9 — Coverage & Fault Analysis.

Consumes trusted Phase 5-8 artifacts (requirements, generated test cases,
execution results, known faults) and produces a traceable AnalysisReport:
requirement coverage, test-category coverage, interface/protocol coverage,
fault-detection analysis, coverage gaps and a serializable summary.

Preview:
    from app.analysis import AnalysisService

    report = AnalysisService.analyze_execution_results(
        requirements, test_cases, results, fault_specs
    )
    print(report.summary.requirement_coverage)
    print(report.summary.fault_detection_rate)
"""

from app.analysis.models import (
    AnalysisReport,
    CategoryTestCoverage,
    CoverageGap,
    CoverageSummary,
    FaultCoverage,
    GapType,
    InterfaceCoverage,
    RequirementCoverage,
    Severity,
    TestCoverage,
)
from app.analysis.service import AnalysisService

__all__ = [
    # models
    "RequirementCoverage",
    "CategoryTestCoverage",
    "TestCoverage",
    "InterfaceCoverage",
    "FaultCoverage",
    "CoverageGap",
    "CoverageSummary",
    "AnalysisReport",
    "GapType",
    "Severity",
    # service
    "AnalysisService",
]
