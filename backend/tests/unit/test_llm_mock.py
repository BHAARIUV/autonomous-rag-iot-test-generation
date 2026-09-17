"""
Phase 7 unit tests: MOCK LLM provider behaviour.

The mock must be deterministic and derive test cases from the actual
requirement (constraints, categories) plus the retrieved knowledge topics —
NOT return the same hard-coded tests for every input.
"""

import json

import pytest

from app.ingestion.models import Constraint, Requirement, RequirementCategory
from app.llm.prompts import build_user_prompt
from app.llm.providers import MockLLMProvider
from app.rag.models import RetrievalResult


REQ_RANGE = Requirement(
    requirement_id="REQ-001",
    description="Temperature must remain between -40 C and 125 C.",
    category=RequirementCategory.RANGE,
    constraints=[
        Constraint(kind="min", value="-40", unit="C"),
        Constraint(kind="max", value="125", unit="C"),
    ],
    source="spec.txt",
    source_reference="line 2",
)

REQ_MQTT = Requirement(
    requirement_id="REQ-004",
    description="The device shall communicate using the MQTT protocol.",
    category=RequirementCategory.COMMUNICATION,
    source="spec.txt",
    source_reference="line 5",
)

REQ_TIMING = Requirement(
    requirement_id="REQ-003",
    description="The device shall produce a new temperature value every 1 s.",
    category=RequirementCategory.TIMING,
    constraints=[Constraint(kind="rate", value="1", unit="s")],
    source="spec.txt",
    source_reference="line 4",
)


def _result(text, topic, chunk_id="kb-x--chunk-000") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id="kb-x",
        text=text,
        source="IoT Test Engineering Handbook",
        title="T",
        topic=topic,
        metadata={"chunk_id": chunk_id},
        distance=0.4,
        relevance=0.6,
    )


@pytest.fixture
def provider():
    return MockLLMProvider()


def _parse(provider, requirement, retrieval=None):
    return json.loads(
        provider.generate("sys-ignored", build_user_prompt(requirement, retrieval))
    )


def test_mock_emits_valid_json_with_test_cases(provider):
    payload = _parse(provider, REQ_RANGE)
    assert "test_cases" in payload
    assert isinstance(payload["test_cases"], list)
    assert len(payload["test_cases"]) >= 1


def test_mock_is_deterministic(provider):
    a = _parse(provider, REQ_RANGE)
    b = _parse(provider, REQ_RANGE)
    assert a == b


def test_mock_traceability_in_every_case(provider):
    payload = _parse(provider, REQ_RANGE)
    for case in payload["test_cases"]:
        assert case["requirement_id"] == "REQ-001"
        assert case["test_data"]["inputs"]


def test_range_requirement_derives_boundaries_and_negatives(provider):
    payload = _parse(provider, REQ_RANGE)
    cats = [c["category"] for c in payload["test_cases"]]
    assert "BOUNDARY" in cats and "NEGATIVE" in cats and "POSITIVE" in cats
    inputs = {c["test_data"]["inputs"]["input"] for c in payload["test_cases"]}
    assert "-40" in inputs and "125" in inputs
    assert "-40.1" in inputs and "125.1" in inputs


def test_mqtt_requirement_derives_communication_tests(provider):
    payload = _parse(provider, REQ_MQTT)
    cats = {c["category"] for c in payload["test_cases"]}
    assert "COMMUNICATION" in cats
    assert all(c["protocol"] == "MQTT" for c in payload["test_cases"])


def test_timing_requirement_derives_timing_tests(provider):
    payload = _parse(provider, REQ_TIMING)
    cats = {c["category"] for c in payload["test_cases"]}
    assert "TIMING" in cats


def test_different_requirements_produce_different_tests(provider):
    range_cases = [json.dumps(c, sort_keys=True) for c in _parse(provider, REQ_RANGE)["test_cases"]]
    mqtt_cases = [json.dumps(c, sort_keys=True) for c in _parse(provider, REQ_MQTT)["test_cases"]]
    assert range_cases != mqtt_cases


def test_equivalence_added_when_knowledge_topic_present(provider):
    without = {c["category"] for c in _parse(provider, REQ_RANGE)["test_cases"]}
    with_ctx = {
        c["category"]
        for c in _parse(
            provider,
            REQ_RANGE,
            [_result("Equivalence partitioning splits the input domain into classes.",
                    "equivalence_partitioning")],
        )["test_cases"]
    }
    assert "EQUIVALENCE" in with_ctx
    assert "EQUIVALENCE" not in without


def test_reliability_added_when_context_supports_it(provider):
    ctx = [
        _result("Offline devices buffer readings and flush them after reconnect.",
                "device_offline_recovery"),
        _result("Fault injection forces sensor and communication failures.",
                "fault_injection"),
    ]
    mqtt_cases = {
        c["category"] for c in _parse(provider, REQ_MQTT, ctx)["test_cases"]
    }
    assert "RELIABILITY" in mqtt_cases


def test_mock_caps_test_count(provider):
    payload = _parse(provider, REQ_RANGE)
    assert len(payload["test_cases"]) <= 8


def test_mock_does_not_invent_specifications(provider):
    req = Requirement(
        requirement_id="REQ-101",
        description="The LED shall blink when the device is booting.",
        category=RequirementCategory.FUNCTIONAL,
        source="spec.txt",
        source_reference="line 9",
    )
    payload = _parse(provider, req)
    first = payload["test_cases"][0]
    # no numeric bounds were supplied, so the mock emits a generic normal-case
    # test — it must NOT fabricate specific LED timing or brightness specs.
    assert first["category"] == "POSITIVE"
    assert "LED" not in first["title"]
    assert "blink" not in first["objective"].lower() or "normal" in first["objective"].lower()


def test_mock_summary_reports_derived_count(provider):
    payload = _parse(provider, REQ_RANGE)
    assert "MOCK" in payload["summary"]
    assert str(len(payload["test_cases"])) in payload["summary"]