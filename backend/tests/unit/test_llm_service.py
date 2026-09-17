"""
Phase 7 unit tests: GenerationService — empty requirements, provider failure,
metadata, RAG source-context preservation, multi-requirement uniqueness, and
deterministic MOCK output.
"""

import json

import pytest

from app.config import Settings
from app.ingestion.models import Constraint, Requirement, RequirementCategory
from app.llm.errors import (
    EmptyRequirementError,
    LLMUnavailableError,
    TestValidationError,
)
from app.llm.models import GeneratedTestSuite, TestCase
from app.llm.providers import LLMProvider, MockLLMProvider
from app.llm.service import GenerationService
from app.rag.models import RetrievalResult


def _req(rid="REQ-001", category=RequirementCategory.RANGE):
    return Requirement(
        requirement_id=rid,
        description="Temperature must remain between -40 C and 125 C.",
        category=category,
        constraints=[
            Constraint(kind="min", value="-40", unit="C"),
            Constraint(kind="max", value="125", unit="C"),
        ],
        source="spec.txt",
        source_reference="line 2",
    )


def _mqtt_req():
    return Requirement(
        requirement_id="REQ-004",
        description="The device shall communicate using the MQTT protocol.",
        category=RequirementCategory.COMMUNICATION,
        source="spec.txt",
        source_reference="line 5",
    )


class StubRag:
    def __init__(self, results):
        self._results = results

    def retrieve_for_requirement(self, requirement, top_k=None):
        return self._results


def _retrieval(chunk_id="kb-bva--chunk-000", topic="boundary_value_analysis"):
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="kb-bva",
        text="Boundary value analysis tests the edges of the valid range.",
        source="IoT Test Engineering Handbook",
        title="BVA",
        topic=topic,
        metadata={"chunk_id": chunk_id},
        distance=0.4,
        relevance=0.6,
    )


def _settings(**overrides) -> Settings:
    values = dict(
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        RAG_TOP_K=4,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeProvider(LLMProvider):
    name = "fake"
    generation_mode = "llm"
    model = "fake-1"

    def __init__(self, payload=None):
        self.payload = payload or {
            "test_cases": [{
                "test_case_id": "TC-001",
                "requirement_id": "REQ-001",
                "title": "Fake title",
                "objective": "Fake objective",
                "category": "POSITIVE",
                "priority": "MEDIUM",
                "test_steps": ["do the thing"],
                "expected_result": "works",
            }]
        }

    def generate(self, system_prompt, user_prompt):
        self.captured = (system_prompt, user_prompt)
        return json.dumps(self.payload)


class BoomProvider(LLMProvider):
    name = "boom"
    generation_mode = "llm"
    model = "boom-1"

    def generate(self, system_prompt, user_prompt):
        raise LLMUnavailableError("provider outage")


@pytest.fixture
def svc():
    return GenerationService(settings_=_settings())


def test_mock_mode_is_default():
    svc = GenerationService(settings_=_settings())
    assert isinstance(svc.provider, MockLLMProvider)


def test_empty_requirement_description_raises(svc):
    blank = _req().model_copy(update={"description": "   "})
    with pytest.raises(EmptyRequirementError):
        svc.generate_for_requirement(blank)


def test_non_requirement_raises(svc):
    with pytest.raises(EmptyRequirementError):
        svc.generate_for_requirement("Temperature -40 to 125")


def test_missing_requirement_id_raises(svc):
    bad = _req().model_copy(update={"requirement_id": ""})
    with pytest.raises(EmptyRequirementError):
        svc.generate_for_requirement(bad)


def test_generate_for_requirement_returns_traceable_suite(svc):
    suite = svc.generate_for_requirement(_req())
    assert isinstance(suite, GeneratedTestSuite)
    assert suite.requirement_id == "REQ-001"
    assert suite.test_cases
    for tc in suite.test_cases:
        assert tc.requirement_id == "REQ-001"
        assert tc.generation_metadata.generation_mode == "mock"
        assert tc.generation_metadata.provider == "mock"


def test_generation_metadata_records_provenance(svc):
    suite = svc.generate_for_requirement(_req())
    meta = suite.generation_metadata
    assert meta.model == "mock-llm"
    assert meta.prompt_version == "phase7-v1"
    assert meta.timestamp
    assert ":" in meta.timestamp


def test_rag_source_context_preserved_when_rag_used():
    rag = StubRag([_retrieval()])
    svc = GenerationService(settings_=_settings(), rag_service=rag)
    suite = svc.generate_for_requirement(_req())
    for tc in suite.test_cases:
        assert tc.source_context is not None
        assert tc.source_context.chunks[0].chunk_id == "kb-bva--chunk-000"
        assert tc.generation_metadata.retrieved_chunk_ids == ["kb-bva--chunk-000"]
        assert tc.source_context.chunks[0].source == "IoT Test Engineering Handbook"


def test_no_rag_service_means_no_source_context(svc):
    suite = svc.generate_for_requirement(_req())
    assert all(tc.source_context is None for tc in suite.test_cases)
    assert suite.generation_metadata.retrieved_chunk_ids == []


def test_provider_failure_propagates_typed_error():
    svc = GenerationService(settings_=_settings(), provider=BoomProvider())
    with pytest.raises(LLMUnavailableError):
        svc.generate_for_requirement(_req())


def test_real_provider_payload_is_parsed_and_validated():
    svc = GenerationService(settings_=_settings(), provider=FakeProvider())
    suite = svc.generate_for_requirement(_req())
    assert len(suite.test_cases) == 1
    assert suite.test_cases[0].title == "Fake title"
    assert suite.generation_metadata.provider == "fake"
    assert suite.generation_metadata.generation_mode == "llm"


def test_invalid_llm_content_is_rejected_not_repaired():
    bad = FakeProvider(payload={"test_cases": [{
        "test_case_id": "TC-001",
        "requirement_id": "REQ-001",
        "title": "x",
        "objective": "x",
        "category": "SORCERY",
        "priority": "MEDIUM",
        "test_steps": ["do"],
        "expected_result": "ok",
    }]})
    svc = GenerationService(settings_=_settings(), provider=bad)
    with pytest.raises(TestValidationError, match="invalid category"):
        svc.generate_for_requirement(_req())


def test_missing_requirement_id_in_llm_output_rejected():
    bad = FakeProvider(payload={"test_cases": [{
        "test_case_id": "TC-001",
        "requirement_id": "REQ-999",  # does not match REQ-001
        "title": "x",
        "objective": "x",
        "category": "POSITIVE",
        "priority": "MEDIUM",
        "test_steps": ["do"],
        "expected_result": "ok",
    }]})
    svc = GenerationService(settings_=_settings(), provider=bad)
    with pytest.raises(TestValidationError, match="mismatch"):
        svc.generate_for_requirement(_req())


def test_multiple_requirements_ids_unique_across_request(svc):
    suites = svc.generate_for_requirements([_req("REQ-001"), _mqtt_req()])
    assert len(suites) == 2
    all_ids = [tc.test_case_id for suite in suites for tc in suite.test_cases]
    assert len(all_ids) == len(set(all_ids))  # globally unique
    # generated in order
    assert suites[0].requirement_id == "REQ-001"
    assert suites[1].requirement_id == "REQ-004"


def test_deterministic_generation(svc):
    first = svc.generate_for_requirement(_req())
    second = svc.generate_for_requirement(_req())
    strip = lambda suite: [tc.model_dump(exclude={"generation_metadata"}) for tc in suite.test_cases]
    assert strip(first) == strip(second)


def test_different_requirements_different_suites(svc):
    range_suite = svc.generate_for_requirement(_req())
    mqtt_suite = svc.generate_for_requirement(_mqtt_req())
    range_cats = {tc.category.value for tc in range_suite.test_cases}
    mqtt_cats = {tc.category.value for tc in mqtt_suite.test_cases}
    assert mqtt_cats <= {"COMMUNICATION", "POSITIVE", "RELIABILITY"}
    assert "BOUNDARY" not in mqtt_cats
    assert "BOUNDARY" in range_cats


def test_provider_sees_prompt_with_requirement(svc):
    svc = GenerationService(settings_=_settings(), provider=FakeProvider())
    svc.generate_for_requirement(_req())
    _system, user = svc.provider.captured
    assert "REQ-001" in user
    assert "Temperature must remain between -40 C and 125 C." in user