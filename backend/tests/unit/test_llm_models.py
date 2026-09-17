"""
Phase 7 unit tests: the generated-test-case data model.
"""

import pytest

from app.llm.models import (
    GeneratedTestSuite,
    GenerationMetadata,
    SourceContext,
    SourceContextItem,
    TestCase,
    TestCategory,
    TestData,
    TestPriority,
    TestStep,
)


def _metadata(provider="mock", mode="mock") -> GenerationMetadata:
    return GenerationMetadata(
        provider=provider,
        model="mock-llm",
        generation_mode=mode,
        prompt_version="phase7-v1",
        timestamp="2026-01-01T00:00:00+00:00",
        retrieved_chunk_ids=["kb-boundary-value-analysis--chunk-000"],
    )


def _test_case() -> TestCase:
    return TestCase(
        test_case_id="TC-001",
        requirement_id="REQ-001",
        title="Minimum boundary value -40 C",
        objective="Verify the minimum bound is accepted.",
        category=TestCategory.BOUNDARY,
        priority=TestPriority.HIGH,
        preconditions=["Device powered"],
        test_steps=[TestStep(step_number=1, action="Drive input to -40 C.")],
        expected_result="Device accepts the value as valid.",
        test_data=TestData(inputs={"temperature": "-40"}, expected={"status": "VALID"}),
        protocol="MQTT",
        interface="iot/sensor/temperature",
        source_context=SourceContext(
            retrieval_query="REQ-001: Temperature must remain between -40 C and 125 C.",
            chunks=[
                SourceContextItem(
                    chunk_id="c1",
                    document_id="kb-1",
                    source="Handbook",
                    title="T",
                    topic="boundary_value_analysis",
                    relevance=0.8,
                )
            ],
        ),
        generation_metadata=_metadata(),
    )


def test_test_case_roundtrips_and_is_frozen():
    tc = _test_case()
    data = tc.model_dump()
    assert data["test_case_id"] == "TC-001"
    assert data["requirement_id"] == "REQ-001"
    assert data["test_steps"][0]["step_number"] == 1
    with pytest.raises(ValueError):
        tc.test_case_id = "TC-999"  # frozen


def _new_test_case(**overrides) -> TestCase:
    data = _test_case().model_dump()
    data.update(overrides)
    return TestCase.model_validate(data)


def test_test_case_requires_at_least_one_step():
    with pytest.raises(ValueError):
        _new_test_case(test_steps=[])


def test_test_case_requires_title_objective_expected_result():
    for field in ("title", "objective", "expected_result"):
        with pytest.raises(ValueError):
            _new_test_case(**{field: ""})


def test_test_step_number_must_be_positive():
    with pytest.raises(ValueError):
        TestStep(step_number=0, action="do")


def test_test_step_action_not_blank():
    with pytest.raises(ValueError):
        TestStep(step_number=1, action="   ")


def test_test_category_members():
    assert {c.value for c in TestCategory} == {
        "POSITIVE", "BOUNDARY", "NEGATIVE", "EQUIVALENCE", "TIMING",
        "COMMUNICATION", "RELIABILITY", "DATA_VALIDATION",
    }


def test_unknown_protocol_rejected():
    with pytest.raises(ValueError):
        _new_test_case(protocol="FTP")


def test_protocol_normalized_upper():
    tc = _new_test_case(protocol="mqtt")
    assert tc.protocol == "MQTT"


def test_metadata_never_stores_secrets():
    meta = _metadata()
    assert "api_key" not in GenerationMetadata.model_fields
    assert "key" not in meta.model_dump()
    assert "token" not in meta.model_dump()


def test_traceability_fields_required():
    tc = _test_case()
    assert tc.requirement_id
    assert tc.test_case_id
    assert tc.source_context is not None
    assert tc.generation_metadata == _metadata()


def test_generated_suite_frozen_and_traceable():
    suite = GeneratedTestSuite(
        requirement_id="REQ-001",
        test_cases=[_test_case()],
        generation_metadata=_metadata(),
    )
    assert suite.requirement_id == "REQ-001"
    assert len(suite.test_cases) == 1
    with pytest.raises(ValueError):
        suite.test_cases = []


def test_source_context_items_carry_full_traceability():
    item = SourceContextItem(
        chunk_id="c1",
        document_id="kb-1",
        source="Handbook",
        title="Boundary Analysis",
        topic="boundary_value_analysis",
        relevance=0.8,
    )
    assert item.chunk_id and item.document_id and item.source and item.title and item.topic


def test_source_context_relevance_bounds():
    with pytest.raises(ValueError):
        SourceContextItem(
            chunk_id="c", document_id="d", source="s", title="t",
            topic="x", relevance=1.5,
        )