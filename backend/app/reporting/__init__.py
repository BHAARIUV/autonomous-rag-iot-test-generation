"""
Phase 10 — Final Reporting & Traceability.

Binds the whole pipeline (requirements -> RAG -> test cases -> validation ->
execution -> faults -> coverage) into one evidence-backed FinalProjectReport,
and writes a machine-readable JSON report plus a human-readable Markdown
report under `reports/`.

Preview:
    from app.reporting import FinalReportService, write_reports

    report = FinalReportService.generate_final_report(
        requirements=..., test_cases=..., results=..., fault_specs=...,
        test_summary=...,
    )
"""

from app.reporting.models import (
    FaultDetectionStatus,
    FaultTraceability,
    FinalProjectReport,
    FinalProjectSummary,
    FinalTestSummary,
    InjectionStatus,
    PhaseEntry,
    PhaseStatus,
    RagEvidence,
    RequirementTraceability,
    TestCaseExecutionLink,
    TestCaseTraceability,
    ValidationStatus,
)
from app.reporting.service import FinalReportService

__all__ = [
    # models
    "PhaseEntry",
    "PhaseStatus",
    "RagEvidence",
    "TestCaseExecutionLink",
    "TestCaseTraceability",
    "RequirementTraceability",
    "FaultTraceability",
    "FaultDetectionStatus",
    "InjectionStatus",
    "ValidationStatus",
    "FinalTestSummary",
    "FinalProjectSummary",
    "FinalProjectReport",
    # service
    "FinalReportService",
]
