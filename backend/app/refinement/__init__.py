"""
Phase 11 — Autonomous Test-Refinement Loop.

Orchestrates the full loop over real Phase 5-9 artifacts:

    results -> analysis -> select gap -> (RAG-aware) generate
    -> validate -> execute -> re-analyse -> compare before/after
    -> repeat until a stop condition (target / max iterations / no improvement /
       no gaps / validation failure / execution error).

It reuses, never re-implements, the existing AnalysisService (Phase 9),
GenerationService (Phases 6/7) and ExecutionService (Phase 8).

Preview:
    from app.refinement import RefinementService

    result = RefinementService(generator=..., executor=...).run(
        requirements=..., test_cases=..., results=..., fault_specs=...
    )
    print(result.stop_reason, result.improvement_requirement_coverage)
"""

from app.refinement.models import (
    CoverageSnapshot,
    RefinementDecision,
    RefinementGap,
    RefinementGapType,
    RefinementIteration,
    RefinementResult,
    StopReason,
)
from app.refinement.service import RefinementService

__all__ = [
    # models
    "StopReason",
    "RefinementDecision",
    "RefinementGapType",
    "RefinementGap",
    "CoverageSnapshot",
    "RefinementIteration",
    "RefinementResult",
    # service
    "RefinementService",
]
