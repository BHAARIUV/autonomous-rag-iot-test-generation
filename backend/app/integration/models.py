"""
Phase 13 — End-to-End Integration models.

WHY:
    The project already has per-phase services (Phases 5-12). Phase 13 adds one
    thin, typed orchestration layer that drives them in a single deterministic
    workflow and records the result of EVERY stage plus full traceability. These
    models are the typed shape of that workflow; every value is derived from the
    real pipeline (real requirement/test/execution/fault/report/dashboard ids and
    numbers) — nothing is fabricated.

HOW (honesty):
    - Each stage has an explicit status (PENDING/SUCCESS/SKIPPED/FAILED), so a
      validation concern is distinguishable from an execution concern.
    - Execution statuses propagate verbatim: ERROR stays ERROR, SKIPPED stays
      SKIPPED — never promoted to PASS.
    - Missing RAG evidence is recorded as an empty list (never invented).
    - Provider mode (MOCK vs REAL LLM) is explicit on the result.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from app.reporting.models import FinalProjectReport


class PipelineStage(str, Enum):
    INGESTION = "INGESTION"
    RAG = "RAG"
    GENERATION = "GENERATION"
    VALIDATION = "VALIDATION"
    EXECUTION = "EXECUTION"
    FAULT_ANALYSIS = "FAULT_ANALYSIS"
    REFINEMENT = "REFINEMENT"
    REPORTING = "REPORTING"
    DASHBOARD = "DASHBOARD"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class StageResult(BaseModel):
    """Outcome of one pipeline stage, fully traceable to real artifacts."""

    model_config = {"frozen": True}

    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    items: int = 0
    message: str = ""
    detail: dict = Field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (StageStatus.SUCCESS, StageStatus.SKIPPED)


class RequirementChainTrace(BaseModel):
    """Per-requirement traceability through the whole chain (real ids)."""

    model_config = {"frozen": True}

    requirement_id: str
    category: str
    description: str
    rag_evidence_chunk_ids: list[str] = Field(default_factory=list)
    generated_test_ids: list[str] = Field(default_factory=list)
    validated_test_ids: list[str] = Field(default_factory=list)
    executed_test_ids: list[str] = Field(default_factory=list)
    coverage_status: str = Field(default="UNCOVERED")
    fault_types: list[str] = Field(default_factory=list)


class RefinementChainSummary(BaseModel):
    """Phase 11 refinement outcome as an e2e stage, honest and traceable."""

    model_config = {"frozen": True}

    applied: bool = False
    stop_reason: str = "Not run"
    coverage_before: float | None = None
    coverage_after: float | None = None
    improvement_requirement_coverage: float | None = None
    total_generated: int = 0
    total_executed: int = 0
    iterations: int = 0


class E2EResult(BaseModel):
    """The complete, typed end-to-end integration run."""

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    specification: str = ""
    provider_mode: str = "MOCK"  # MOCK / REAL LLM (never hidden)

    stages: list[StageResult] = Field(default_factory=list)
    requirements: list[RequirementChainTrace] = Field(default_factory=list)

    total_requirements: int = 0
    total_tests: int = 0
    validated_count: int = 0
    executed_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    skipped_count: int = 0

    broker_reachable: bool | None = None
    report: FinalProjectReport | None = None
    refinement: RefinementChainSummary = Field(default_factory=RefinementChainSummary)
    dashboard_available: bool = False
    dashboard_summary: dict = Field(default_factory=dict)


def stage(stage: PipelineStage, *, status=StageStatus.SUCCESS, items=0,
          message="", detail=None, error=None) -> StageResult:
    return StageResult(
        stage=stage, status=status, items=items, message=message,
        detail=detail or {}, error=error,
    )


def stages_to_map(stages: list[StageResult]) -> dict[str, StageResult]:
    return {s.stage.value: s for s in stages}


__all__ = [
    "PipelineStage",
    "StageStatus",
    "StageResult",
    "RequirementChainTrace",
    "RefinementChainSummary",
    "E2EResult",
    "stage",
    "stages_to_map",
]
