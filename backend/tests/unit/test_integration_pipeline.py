"""Phase 13 integration orchestrator unit tests (honest propagation)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.integration.pipeline import (
    E2EPipeline,
    _broker_reachable,
    _status_counts,
)

_MOCK_CFG = Settings(
    _env_file=None,
    LLM_PROVIDER="mock",
    LLM_MODEL="mock-llm",
    EMBEDDING_PROVIDER="local",
    EMBEDDING_DIMENSION=256,
    RAG_TOP_K=2,
)


class _R:
    """Minimal fake ExecutionResult exposing only `status`."""

    def __init__(self, status):
        self.status = status


class TestStatusCounts:
    def test_counts_each_status_verbatim(self):
        from app.testing.models import TestStatus

        results = [
            _R(TestStatus.PASS), _R(TestStatus.PASS),
            _R(TestStatus.FAIL), _R(TestStatus.ERROR), _R(TestStatus.SKIPPED),
        ]
        c = _status_counts(results)
        assert c == {"total": 5, "passed": 2, "failed": 1, "errors": 1, "skipped": 1}

    def test_error_never_becomes_pass(self):
        from app.testing.models import TestStatus

        c = _status_counts([_R(TestStatus.ERROR)])
        assert c["errors"] == 1
        assert c["passed"] == 0

    def test_skipped_never_becomes_pass(self):
        from app.testing.models import TestStatus

        c = _status_counts([_R(TestStatus.SKIPPED)])
        assert c["skipped"] == 1
        assert c["passed"] == 0


class TestCoverageStatus:
    def test_uncovered_when_no_tests(self):
        assert E2EPipeline._coverage_status([], []) == "UNCOVERED"

    def test_failed_when_any_fail(self):
        from app.testing.models import TestStatus

        assert E2EPipeline._coverage_status(["tc"], [_R(TestStatus.FAIL)]) == "FAILED"
        assert E2EPipeline._coverage_status(["tc"], [_R(TestStatus.FAIL), _R(TestStatus.PASS)]) == "FAILED"

    def test_covered_only_on_pass(self):
        from app.testing.models import TestStatus

        assert E2EPipeline._coverage_status(["tc"], [_R(TestStatus.PASS)]) == "COVERED"

    def test_skipped_error_label_when_never_passed_or_failed(self):
        from app.testing.models import TestStatus

        assert E2EPipeline._coverage_status(["tc"], [_R(TestStatus.SKIPPED)]) == "SKIPPED/ERROR"


class TestBrokerProbe:
    def test_reachable_broker_is_true(self):
        assert _broker_reachable(_MOCK_CFG) is True

    def test_unreachable_broker_is_false(self):
        cfg = _MOCK_CFG.model_copy(update={"mqtt_broker_port": 1})
        assert _broker_reachable(cfg) is False


class TestPipelineFailureHonesty:
    def test_empty_spec_fails_ingestion_honestly(self):
        result = E2EPipeline(settings_=_MOCK_CFG).run(
            "   ", source="empty.txt", top_k=2
        )
        ing = next((s for s in result.stages if s.stage.value == "INGESTION"), None)
        assert ing is not None
        assert ing.status.value == "FAILED"
        assert ing.error
        assert result.total_requirements == 0


class TestPipelineGeneratorFailure:
    def test_generator_failure_propagates_failed_status(self):
        class _BrokenGen:
            def generate_for_requirements(self, requirements, **kwargs):
                raise RuntimeError("generator boom")

        result = E2EPipeline(
            settings_=_MOCK_CFG, generator=_BrokenGen(),
        ).run("Range: -40 C to 125 C\n", source="s.txt", top_k=2)
        gen = next((s for s in result.stages if s.stage.value == "GENERATION"), None)
        rag = next((s for s in result.stages if s.stage.value == "RAG"), None)
        assert gen is not None and gen.status.value == "FAILED"
        assert rag is not None and rag.status.value in ("SUCCESS", "FAILED")
        assert result.report is None
