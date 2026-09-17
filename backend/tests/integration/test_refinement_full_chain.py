"""
Phase 11 integration test — the autonomous refinement loop over the REAL
Phase 5->6->7->8->9 artifacts (mock LLM, local embeddings, shipped knowledge
corpus, and the real MQTT broker for safe execution).

Scenario:
  ingest spec -> generate a DELIBERATELY incomplete suite (only REQ-001)
  -> execute it -> run RefinementService -> assert it closes the uncovered
  requirement gaps via RAG-aware regeneration, drives requirement coverage up,
  and stops with an explicit reason.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.ingestion.service import ingest_text
from app.llm.models import TestCase
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.refinement import RefinementService, StopReason
from app.testing import ExecutionService


_DEMO_SPEC = """Device: Temperature Sensor
Range: -40 C to 125 C
Accuracy: 0.5 C
Sampling Interval: 1 s
Communication Protocol: MQTT
"""


def _settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path / "chroma"),
        RAG_COLLECTION_NAME="int_refine_knowledge",
        RAG_CHUNK_SIZE=600,
        RAG_CHUNK_OVERLAP=80,
        RAG_TOP_K=4,
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
    )


@pytest.fixture
def full_pipeline(tmp_path):
    cfg = _settings(tmp_path)
    rag = RagService(settings_=cfg)
    rag.index_knowledge_base()
    generator = GenerationService(settings_=cfg, rag_service=rag)
    executor = ExecutionService(settings_=cfg)
    yield cfg, generator, executor
    rag.close()


def _phase5(full_pipeline):
    _, _, _ = full_pipeline
    spec = ingest_text(_DEMO_SPEC, source="temperature_sensor.txt")
    return list(spec.requirements)


def test_refinement_closes_uncovered_requirement_gaps(full_pipeline):
    cfg, generator, executor = full_pipeline
    reqs = _phase5(full_pipeline)
    req_by_id = {r.requirement_id: r for r in reqs}

    # IMCOMPLETE start: only REQ-001 generated + executed.
    suite = generator.generate_for_requirement(req_by_id["REQ-001"], top_k=4)
    assert isinstance(suite.test_cases[0], TestCase)
    results, _ = executor.execute_test_cases(suite.test_cases)

    service = RefinementService(
        settings_=cfg, generator=generator, executor=executor,
        max_iterations=6, target_requirement_coverage=90.0,
    )
    result = service.run(requirements=reqs, test_cases=suite.test_cases,
                         results=results, fault_specs=[])

    assert result.initial_coverage.requirement_coverage < 100.0
    assert result.stop_reason is StopReason.TARGET_REACHED
    assert result.final_coverage.requirement_coverage >= 90.0
    assert result.improvement_requirement_coverage > 0
    assert result.total_generated > 0
    assert result.total_executed > 0
    assert len(result.iterations) >= 1
    # every generated test was validated by Phase 7 before entering execution
    assert all(it.validation_outcome in ("VALIDATED", "NONE") for it in result.iterations)
    # before -> after coverage strictly never decreases
    covs = [it.coverage_before.requirement_coverage for it in result.iterations]
    afters = [it.coverage_after.requirement_coverage for it in result.iterations]
    assert covs == sorted(covs)
    assert all(a >= b for a, b in zip(afters, [result.initial_coverage.requirement_coverage] + covs))


def test_refinement_max_iterations_is_respected(full_pipeline):
    cfg, generator, executor = full_pipeline
    reqs = _phase5(full_pipeline)
    req_by_id = {r.requirement_id: r for r in reqs}

    suite = generator.generate_for_requirement(req_by_id["REQ-001"], top_k=4)
    results, _ = executor.execute_test_cases(suite.test_cases)

    # target is unreachable within 1 iteration -> MAX_ITERATIONS, but the loop
    # still returns fully-traceable, measurable results (no fabricated numbers).
    service = RefinementService(
        settings_=cfg, generator=generator, executor=executor,
        max_iterations=1, target_requirement_coverage=100.0,
    )
    result = service.run(requirements=reqs, test_cases=suite.test_cases,
                         results=results, fault_specs=[])
    assert result.stop_reason is StopReason.MAX_ITERATIONS
    assert len(result.iterations) == 1
    assert result.initial_coverage.requirement_coverage < result.final_coverage.requirement_coverage
    assert result.improvement_requirement_coverage >= 0
