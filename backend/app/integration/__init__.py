"""
Phase 13 — End-to-End Integration.

Re-exports the orchestration layer and its typed models so callers use one
public surface (consistent with the other phase packages).
"""

from app.integration.models import (
    E2EResult,
    PipelineStage,
    RefinementChainSummary,
    RequirementChainTrace,
    StageResult,
    StageStatus,
    stage,
    stages_to_map,
)
from app.integration.pipeline import E2EPipeline

__all__ = [
    "E2EPipeline",
    "E2EResult",
    "PipelineStage",
    "RefinementChainSummary",
    "RequirementChainTrace",
    "StageResult",
    "StageStatus",
    "stage",
    "stages_to_map",
]
