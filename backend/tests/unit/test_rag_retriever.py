"""
Phase 6 unit tests: Retriever — query validation, top_k behaviour and
structured result delivery.
"""

import pytest

from app.rag.embeddings import HashingEmbeddingProvider
from app.rag.errors import InvalidQueryError
from app.rag.models import Chunk, RetrievalResult
from app.rag.retriever import Retriever
from app.rag.vector_store import ChromaVectorStore


def _chunk(chunk_id, text, topic, document_id="kb-x"):
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text=text,
        title="T",
        source="Handbook",
        topic=topic,
        version="1.0",
        document_type="knowledge",
        chunk_index=0,
        chunk_total=1,
    )


CORPUS = [
    _chunk("c-boundary", "Boundary Value Analysis tests the edges of ranges such as minus 40 and 125 Celsius.", "boundary_value_analysis"),
    _chunk("c-temp", "Temperature sensor range and accuracy testing from minus 40 Celsius to 125 Celsius.", "temperature_sensor_testing"),
    _chunk(
        "c-mqtt",
        "MQTT publish subscribe with QoS levels and broker reconnection after network loss.",
        "mqtt_testing",
    ),
    _chunk(
        "c-offline",
        "Device goes offline, buffers readings, and reconnects to flush pending messages.",
        "device_offline_recovery",
    ),
    _chunk(
        "c-negative",
        "Negative testing with out of range values and malformed payloads rejected safely.",
        "negative_testing",
    ),
    _chunk("c-fault", "Fault injection forces sensor and communication failures.", "fault_injection"),
]


@pytest.fixture
def retriever():
    store = ChromaVectorStore("test_rag_retriever", ephemeral=True)
    provider = HashingEmbeddingProvider(dimension=256)
    r = Retriever(store, provider, default_top_k=3)
    chunks = CORPUS
    store.add_chunks(chunks, provider.embed_documents([c.text for c in chunks]))
    yield r, store
    store.close()


def test_retrieve_returns_structured_results(retriever):
    r, _ = retriever
    results = r.retrieve("temperature range boundary", top_k=2)
    assert results
    for result in results:
        assert isinstance(result, RetrievalResult)
        assert result.chunk_id and result.text and result.source
        assert result.metadata["document_id"] == "kb-x"
        assert 0.0 <= result.relevance <= 1.0


def test_retrieve_topics_relevant(retriever):
    r, _ = retriever
    results = r.retrieve(
        "temperature must stay within the declared range and be accurate",
        top_k=3,
    )
    topics = {res.topic for res in results}
    assert "temperature_sensor_testing" in topics


def test_mqtt_query_finds_mqtt(retriever):
    r, _ = retriever
    results = r.retrieve("mqtt publish subscribe qos reconnect", top_k=2)
    assert results[0].topic == "mqtt_testing"


def test_default_top_k_used(retriever):
    r, _ = retriever
    results = r.retrieve("temperature")
    assert len(results) == 3  # default_top_k=3


def test_top_k_larger_than_corpus_returns_all(retriever):
    r, _ = retriever
    assert len(r.retrieve("temperature", top_k=100)) == len(CORPUS)


def test_blank_query_raises(retriever):
    r, _ = retriever
    with pytest.raises(InvalidQueryError):
        r.retrieve("")
    with pytest.raises(InvalidQueryError):
        r.retrieve("   \n  ")


def test_zero_or_negative_top_k_raises(retriever):
    r, _ = retriever
    with pytest.raises(InvalidQueryError):
        r.retrieve("temperature", top_k=0)
    with pytest.raises(InvalidQueryError):
        r.retrieve("temperature", top_k=-3)


def test_retrieve_on_empty_store_returns_empty():
    store = ChromaVectorStore("empty_retriever", ephemeral=True)
    r = Retriever(store, HashingEmbeddingProvider(dimension=32), default_top_k=2)
    assert r.retrieve("anything") == []
    store.close()