"""Phase 13 integration models + stage-helper unit tests."""

from __future__ import annotations

import pytest

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


class TestStageHelpers:
    def test_stage_defaults_to_success(self):
        s = stage(PipelineStage.INGESTION, items=3)
        assert s.status is StageStatus.SUCCESS
        assert s.ok is True
        assert s.items == 3

    def test_stage_can_be_failed(self):
        s = stage(PipelineStage.EXECUTION, status=StageStatus.FAILED, error="boom")
        assert s.ok is False
        assert s.error == "boom"

    def test_stage_skipped_is_ok(self):
        s = stage(PipelineStage.DASHBOARD, status=StageStatus.SKIPPED)
        assert s.ok is True

    @pytest.mark.parametrize("status,expected", [
        (StageStatus.SUCCESS, True),
        (StageStatus.SKIPPED, True),
        (StageStatus.FAILED, False),
        (StageStatus.PENDING, False),
    ])
    def test_ok_semantics(self, status, expected):
        s = StageResult(stage=PipelineStage.RAG, status=status)
        assert s.ok is expected

    def test_stage_result_is_frozen(self):
        s = stage(PipelineStage.RAG)
        with pytest.raises(Exception):
            s.items = 99

    def test_stages_to_map_keys_by_stage_value(self):
        stages = [
            stage(PipelineStage.INGESTION),
            stage(PipelineStage.EXECUTION, status=StageStatus.FAILED),
        ]
        m = stages_to_map(stages)
        assert set(m) == {"INGESTION", "EXECUTION"}
        assert m["EXECUTION"].status is StageStatus.FAILED


class TestE2EResult:
    def test_defaults(self):
        r = E2EResult()
        assert r.run_id
        assert r.provider_mode == "MOCK"
        assert r.stages == []
        assert r.total_tests == 0
        assert r.report is None
        assert r.dashboard_available is False
        assert isinstance(r.refinement, RefinementChainSummary)
        assert r.refinement.applied is False

    def test_e2e_result_is_mutable_for_pipeline_population(self):
        # E2EResult is the pipeline's accumulator: stages/report/etc. are set
        # after construction, so it must NOT be frozen.
        r = E2EResult()
        r.stages = [stage(PipelineStage.RAG)]
        r.total_tests = 5
        assert r.total_tests == 5


class TestTraceModels:
    def test_requirement_trace_defaults(self):
        t = RequirementChainTrace(requirement_id="REQ-001", category="RANGE", description="d")
        assert t.rag_evidence_chunk_ids == []
        assert t.generated_test_ids == []
        assert t.coverage_status == "UNCOVERED"
        assert t.fault_types == []

    def test_refinement_summary_defaults(self):
        s = RefinementChainSummary()
        assert s.applied is False
        assert s.stop_reason == "Not run"
        assert s.coverage_before is None
