"""
Phase 6 integration test: a Phase 5 requirement flows through RAG retrieval and
returns the relevant testing knowledge.

    Phase 5 requirement (temperature range REQ-001)
        -> retrieve_for_requirement()
        -> Boundary Value Analysis / range-testing knowledge

This test is fully offline: it uses the shipped knowledge corpus under
`knowledge_base/documents`, the deterministic local hashing embeddings, and a
temporary Chroma store. No external API and no MQTT broker are required.
"""

import pytest

from app.config import Settings
from app.ingestion.service import ingest_text
from app.rag.models import RetrievalResult
from app.rag.service import RagService

_DEMO_SPEC = """Device: Temperature Sensor
Range: -40 C to 125 C
Accuracy: 0.5 C
Sampling Interval: 1 s
Communication Protocol: MQTT
"""


@pytest.fixture
def rag(tmp_path):
    cfg = Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path / "chroma"),
        RAG_COLLECTION_NAME="int_iot_knowledge",
        RAG_CHUNK_SIZE=600,
        RAG_CHUNK_OVERLAP=80,
        RAG_TOP_K=4,
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
    )
    service = RagService(settings_=cfg)
    index = service.index_knowledge_base()
    assert index.document_count == 12
    assert index.chunk_count >= 12
    yield service
    service.close()


@pytest.fixture
def phase5_requirements():
    spec = ingest_text(_DEMO_SPEC, source="temperature_sensor.txt")
    by_id = {r.requirement_id: r for r in spec.requirements}
    assert by_id["REQ-001"].category.value == "RANGE"
    assert by_id["REQ-002"].category.value == "ACCURACY"
    return by_id


def test_full_chain_phase5_to_rag_knowledge(rag, phase5_requirements):
    req = phase5_requirements["REQ-001"]
    results = rag.retrieve_for_requirement(req, top_k=4)

    assert results, "expected relevant knowledge for the range requirement"
    for result in results:
        assert isinstance(result, RetrievalResult)
        assert result.text
        # source traceability is preserved end-to-end
        assert result.source == "IoT Test Engineering Handbook"
        assert result.document_id.startswith("kb-")
        assert result.metadata["chunk_id"] == result.chunk_id
        assert 0.0 <= result.relevance <= 1.0
        assert result.distance >= 0.0

    # distances come back nearest-first
    distances = [r.distance for r in results]
    assert distances == sorted(distances)

    # the requirement asks about the -40..125 temperature range: the knowledge
    # retrieved must include range/boundary analysis and temperature sensor
    # range-testing, NOT an unrelated topic such as MQTT testing.
    topics = {r.topic for r in results}
    assert "temperature_sensor_testing" in topics
    assert "boundary_value_analysis" in topics
    assert "mqtt_testing" not in topics


def test_accuracy_requirement_retrieves_accuracy_knowledge(rag, phase5_requirements):
    req = phase5_requirements["REQ-002"]  # ±0.5 °C accuracy
    results = rag.retrieve_for_requirement(req, top_k=4)
    topics = {r.topic for r in results}
    assert "sensor_accuracy" in topics


def test_mqtt_requirement_retrieves_mqtt_knowledge(rag, phase5_requirements):
    req = phase5_requirements["REQ-004"]  # Communication Protocol: MQTT
    results = rag.retrieve_for_requirement(req, top_k=4)
    topics = {r.topic for r in results}
    assert "mqtt_testing" in topics


def test_top_k_is_honoured(rag, phase5_requirements):
    req = phase5_requirements["REQ-001"]
    assert len(rag.retrieve_for_requirement(req, top_k=3)) == 3
    assert len(rag.retrieve_for_requirement(req, top_k=1)) == 1
    assert len(rag.retrieve_for_requirement(req, top_k=50)) == rag.store.count()