"""
Phase 6 unit tests: ChromaVectorStore — indexing, duplicate avoidance, query
ordering, filtering basics, clear/rebuild, and persistence across close/reopen.
"""

import pytest

from app.rag.errors import VectorStoreError
from app.rag.models import Chunk
from app.rag.vector_store import ChromaVectorStore


def _chunk(chunk_id, document_id="kb-a", text="knowledge chunk text", topic="x"):
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


@pytest.fixture
def store():
    s = ChromaVectorStore("test_rag_vs", ephemeral=True)
    yield s
    s.close()


def test_add_and_count(store):
    result = store.add_chunks(
        [_chunk("c1"), _chunk("c2")],
        [[0.1, 0.2], [0.3, 0.4]],
    )
    assert result.added == 2
    assert result.skipped_duplicates == 0
    assert store.count() == 2


def test_duplicate_add_skipped(store):
    store.add_chunks([_chunk("c1")], [[0.1, 0.2]])
    result = store.add_chunks([_chunk("c1"), _chunk("c2")], [[0.1, 0.2], [0.5, 0.6]])
    assert result.added == 1
    assert result.skipped_duplicates == 1
    assert store.count() == 2
    assert "c1" in store.known_chunk_ids()


def test_known_chunk_ids(store):
    store.add_chunks(
        [_chunk("a", document_id="kb-1"), _chunk("b", document_id="kb-2")],
        [[0.0, 1.0], [1.0, 0.0]],
    )
    assert store.known_chunk_ids() == {"a", "b"}
    assert store.document_ids() == {"kb-1", "kb-2"}


def test_query_returns_nearest_first(store):
    store.add_chunks(
        [
            _chunk("near", text="boundary value analysis"),
            _chunk("mid", text="electrical wiring notes"),
            _chunk("far", text="cooking recipes"),
        ],
        [
            [0.9, 0.1, 0.0],
            [0.5, 0.4, 0.0],
            [0.0, 0.0, 1.0],
        ],
    )
    results = store.query([1.0, 0.0, 0.0], top_k=2)
    assert [r.chunk_id for r in results] == ["near", "mid"]
    assert results[0].distance <= results[1].distance
    assert results[0].relevance >= results[1].relevance


def test_query_result_fields(store):
    store.add_chunks([_chunk("c1", document_id="kb-b", topic="mqtt_testing")], [[0.5, 0.5]])
    (result,) = store.query([0.5, 0.5], top_k=1)
    assert result.chunk_id == "c1"
    assert result.document_id == "kb-b"
    assert result.source == "Handbook"
    assert result.topic == "mqtt_testing"
    assert result.metadata["chunk_id"] == "c1"
    assert result.text == "knowledge chunk text"
    assert 0.0 <= result.relevance <= 1.0
    assert result.distance >= 0.0


def test_query_empty_store(store):
    assert store.query([0.1, 0.2], top_k=3) == []


def test_query_bad_top_k_raises(store):
    with pytest.raises(VectorStoreError):
        store.query([0.1], top_k=0)


def test_add_chunk_embedding_mismatch_raises(store):
    with pytest.raises(VectorStoreError):
        store.add_chunks([_chunk("c1")], [[0.1, 0.2], [0.3, 0.4]])


def test_clear_then_readd(store):
    store.add_chunks(
        [_chunk("a"), _chunk("b")],
        [[0.1, 0.2], [0.2, 0.1]],
    )
    assert store.count() == 2
    store.clear()
    assert store.count() == 0
    assert store.known_chunk_ids() == set()
    store.add_chunks([_chunk("a")], [[0.1, 0.2]])
    assert store.count() == 1


def test_persistence_across_close_and_reopen(tmp_path):
    persist = str(tmp_path / "chroma")
    store = ChromaVectorStore("persist_kb", persist_dir=persist)
    store.add_chunks([_chunk("p1")], [[0.4, 0.6]])
    store.close()

    reopened = ChromaVectorStore("persist_kb", persist_dir=persist)
    assert reopened.count() == 1
    (result,) = reopened.query([0.4, 0.6], top_k=1)
    assert result.chunk_id == "p1"
    reopened.close()


def test_short_collection_name_rejected():
    with pytest.raises(VectorStoreError):
        ChromaVectorStore("ab", ephemeral=True)