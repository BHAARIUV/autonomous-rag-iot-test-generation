"""
Phase 12 — Dashboard view models.

WHY:
    The dashboard is a READ-ONLY reporting layer. These view models are the
    typed shape the renderer consumes. Every field is derived from REAL project
    data (the Phase 10 final report, the RAG corpus manifest, the Phase 11
    refinement result, actual pytest counts). Missing values are surfaced as
    the string "Not available" — never an invented number.

HOW:
    - `dashboard/provider.py` loads/reads real data (read-only).
    - `dashboard/service.py` folds that data into these models.
    - `dashboard/render.py` renders them (HTML / text).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


def not_available() -> str:
    return "Not available"


class OverviewView(BaseModel):
    """Section A — project overview."""

    project_name: str
    project_id: str = not_available()
    project_status: str = not_available()
    current_phase: int | None = None
    completed_phases: int = 0
    total_phases: int = 0

    total_requirements: int | None = None
    total_test_cases: int | None = None
    executed_tests: int | None = None
    passed: int | None = None
    failed: int | None = None
    errors: int | None = None
    skipped: int | None = None
    generation_mode: str = not_available()

    analysis_id: str = ""


class RequirementView(BaseModel):
    """Section B — one requirement row."""

    requirement_id: str
    category: str
    description: str
    validation_status: str = not_available()
    test_case_count: int = 0
    coverage_status: str = not_available()  # COVERED / PARTIALLY COVERED / UNCOVERED


class KnowledgeDocView(BaseModel):
    """One knowledge document from the RAG corpus manifest."""

    document_id: str
    title: str
    topic: str = not_available()
    source: str = not_available()
    version: str = not_available()


class RequirementKnowledgeView(BaseModel):
    """Requirement -> retrieved knowledge mapping (real retrieval evidence)."""

    requirement_id: str
    retrieval_count: int = 0
    topics: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    chunks: list[str] = Field(default_factory=list)


class KnowledgeView(BaseModel):
    """Section C — RAG / knowledge."""

    corpus_description: str = not_available()
    corpus_version: str = not_available()
    document_count: int = 0
    semantic_metrics: bool = False
    documents: list[KnowledgeDocView] = Field(default_factory=list)
    requirement_mapping: list[RequirementKnowledgeView] = Field(default_factory=list)
    retrieved_topics: list[str] = Field(default_factory=list)


class GeneratedTestView(BaseModel):
    """Section D — one generated test case row."""

    test_case_id: str
    requirement_id: str
    category: str
    priority: str
    generation_mode: str = not_available()  # MOCK / REAL LLM (never hidden)
    validation_status: str = not_available()
    duplicate_rejected: str = "Not available"


class GenerationView(BaseModel):
    """Section D — test generation."""

    total_generated: int = 0
    generation_mode: str = not_available()  # MOCK / REAL LLM
    tests: list[GeneratedTestView] = Field(default_factory=list)


class ExecutionView(BaseModel):
    """Section E — test execution."""

    total_executed: int | None = None
    passed: int | None = None
    failed: int | None = None
    errors: int | None = None
    skipped: int | None = None
    execution_coverage: float | None = None
    execution_history: list[dict] = Field(default_factory=list)


class FaultView(BaseModel):
    """Section F — one fault row (detection never inferred)."""

    fault_id: str
    fault_type: str
    detection_status: str = not_available()
    injection_status: str = not_available()
    requirement_ids: list[str] = Field(default_factory=list)
    related_test_case_ids: list[str] = Field(default_factory=list)
    detection_evidence: str = not_available()
    execution_result: str = "Not available"


class FaultSummaryView(BaseModel):
    """Section F — fault analysis summary."""

    total_faults: int | None = None
    detected_faults: int | None = None
    missed_faults: int | None = None
    fault_detection_rate: float | None = None
    faults: list[FaultView] = Field(default_factory=list)


class RefinementIterationView(BaseModel):
    """One Phase 11 refinement iteration (real measured values)."""

    iteration_number: int
    decision: str = not_available()
    gap_type: str = not_available()
    generated: int = 0
    executed: int = 0
    coverage_before: float | None = None
    coverage_after: float | None = None
    improvement: float = 0.0


class RefinementView(BaseModel):
    """Section G — Phase 11 refinement result (real, computed mock-mode)."""

    available: bool = False
    stop_reason: str = not_available()
    gaps_before: int | None = None
    gaps_after: int | None = None
    coverage_before: float | None = None
    coverage_after: float | None = None
    improvement_requirement_coverage: float | None = None
    total_generated: int = 0
    total_executed: int = 0
    iterations: list[RefinementIterationView] = Field(default_factory=list)


class TraceabilityRowView(BaseModel):
    """Section H — one requirement's end-to-end trace row (real ids)."""

    requirement_id: str
    rag_evidence_count: int = 0
    rag_evidence: list[str] = Field(default_factory=list)  # chunk ids
    test_case_ids: list[str] = Field(default_factory=list)
    validation_status: str = not_available()
    execution_ids: list[str] = Field(default_factory=list)
    execution_status: str = not_available()
    fault_types: list[str] = Field(default_factory=list)
    fault_detection: str = not_available()
    coverage: str = not_available()
    refined: bool = False


class TraceabilityView(BaseModel):
    """Section H — traceability."""

    rows: list[TraceabilityRowView] = Field(default_factory=list)


class PhaseStatusView(BaseModel):
    """One phase's status in the final project status view."""

    phase_number: int
    title: str = not_available()
    status: str = not_available()
    verification: str = ""


class FinalStatusView(BaseModel):
    """Section I — final project status."""

    phases: list[PhaseStatusView] = Field(default_factory=list)
    final_test_result: dict = Field(default_factory=dict)
    requirement_coverage: float | None = None
    execution_coverage: float | None = None
    fault_detection: float | None = None
    remaining_gaps: int | None = None
    known_limitations: list[str] = Field(default_factory=list)


class DashboardData(BaseModel):
    """The complete set of dashboard sections (A-I)."""

    overview: OverviewView
    requirements: list[RequirementView] = Field(default_factory=list)
    knowledge: KnowledgeView
    generation: GenerationView
    execution: ExecutionView
    fault_summary: FaultSummaryView
    refinement: RefinementView
    traceability: TraceabilityView
    final_status: FinalStatusView


__all__ = [
    "not_available",
    "OverviewView",
    "RequirementView",
    "KnowledgeDocView",
    "RequirementKnowledgeView",
    "KnowledgeView",
    "GeneratedTestView",
    "GenerationView",
    "ExecutionView",
    "FaultView",
    "FaultSummaryView",
    "RefinementIterationView",
    "RefinementView",
    "TraceabilityRowView",
    "TraceabilityView",
    "PhaseStatusView",
    "FinalStatusView",
    "DashboardData",
]
