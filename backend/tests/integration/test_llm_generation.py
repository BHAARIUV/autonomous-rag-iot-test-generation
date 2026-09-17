"""
Phase 7 integration test (MOCK mode, fully offline):

    Phase 5 requirement (temperature range)
        -> Phase 6 RAG retrieval (real shipped corpus, temp Chroma store)
        -> Phase 7 LLM test generation (MOCK provider)
        -> validated, traceable structured test cases

No API key, no network, no broker required. `generation_mode == 'mock'` is
explicitly asserted so this never masquerades as a real-LLM run.
"""

import pytest

from app.config import Settings
from app.ingestion.service import ingest_text
from app.llm.models import GeneratedTestSuite, TestCase, TestCategory
from app.llm.service import GenerationService
from app.rag.service import RagService

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
        RAG_COLLECTION_NAME="int_llm_knowledge",
        RAG_CHUNK_SIZE=600,
        RAG_CHUNK_OVERLAP=80,
        RAG_TOP_K=4,
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
    )


@pytest.fixture
def pipeline(tmp_path):
    cfg = _settings(tmp_path)
    rag = RagService(settings_=cfg)
    index = rag.index_knowledge_base()
    assert index.document_count == 12
    service = GenerationService(settings_=cfg, rag_service=rag)
    yield service, rag
    rag.close()


@pytest.fixture
def phase5_requirements():
    spec = ingest_text(_DEMO_SPEC, source="temperature_sensor.txt")
    return {r.requirement_id: r for r in spec.requirements}


def test_phase5_to_rag_to_llm_full_chain_mock(pipeline, phase5_requirements):
    service, rag = pipeline
    requirement = phase5_requirements["REQ-001"]  # range -40..125 C
    suite = service.generate_for_requirement(requirement, top_k=4)

    assert isinstance(suite, GeneratedTestSuite)
    assert suite.requirement_id == "REQ-001"

    # explicit: this run is MOCK, not a real LLM
    assert suite.generation_metadata.generation_mode == "mock"
    assert suite.generation_metadata.provider == "mock"
    assert suite.generation_metadata.prompt_version == "phase7-v1"

    assert len(suite.test_cases) >= 4
    for tc in suite.test_cases:
        assert isinstance(tc, TestCase)
        assert tc.requirement_id == "REQ-001"  # traceability
        assert tc.test_steps and tc.test_steps[0].step_number == 1
        assert tc.expected_result
        assert tc.objective
        # RAG knowledge used is preserved and matches the retrieval metadata
        assert tc.source_context is not None
        assert len(tc.source_context.chunks) == len(tc.generation_metadata.retrieved_chunk_ids)
        assert tc.source_context.chunks[0].source == "IoT Test Engineering Handbook"

    # the -40..125 range requirement must produce boundary + negative tests
    categories = {tc.category for tc in suite.test_cases}
    assert TestCategory.BOUNDARY in categories
    assert TestCategory.NEGATIVE in categories

    # boundary and negative tests use values derived from the actual bounds
    boundary_values = [
        tc.test_data.inputs["input"]
        for tc in suite.test_cases
        if tc.category is TestCategory.BOUNDARY
    ]
    assert "-40" in boundary_values and "125" in boundary_values

    # retrieved context is the expected knowledge for the range requirement
    topics = {c.topic for tc in suite.test_cases for c in (tc.source_context.chunks if tc.source_context else [])}
    assert "boundary_value_analysis" in topics
    assert "temperature_sensor_testing" in topics
    assert "negative_testing" in topics


def test_mqtt_requirement_gets_communication_tests(pipeline, phase5_requirements):
    service, _ = pipeline
    requirement = phase5_requirements["REQ-004"]  # MQTT protocol
    suite = service.generate_for_requirement(requirement, top_k=4)
    categories = {tc.category for tc in suite.test_cases}
    assert TestCategory.COMMUNICATION in categories
    assert all(tc.protocol == "MQTT" for tc in suite.test_cases)


def test_two_requirements_share_unique_ids(pipeline, phase5_requirements):
    service, _ = pipeline
    suites = service.generate_for_requirements(
        [phase5_requirements["REQ-001"], phase5_requirements["REQ-004"]]
    )
    ids = [tc.test_case_id for suite in suites for tc in suite.test_cases]
    assert len(ids) == len(set(ids))
    assert suites[0].requirement_id == "REQ-001"
    assert suites[1].requirement_id == "REQ-004"


def test_deterministic_across_runs(pipeline, phase5_requirements):
    service, _ = pipeline
    requirement = phase5_requirements["REQ-001"]
    first = service.generate_for_requirement(requirement)
    second = service.generate_for_requirement(requirement)
    strip = lambda suite: [tc.model_dump(exclude={"generation_metadata"}) for tc in suite.test_cases]
    assert strip(first) == strip(second)