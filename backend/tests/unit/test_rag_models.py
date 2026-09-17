"""
Phase 6 unit tests: RAG data models — RagDocument / Chunk / RetrievalResult /
IndexResult contracts (frozen, validated, metadata preservation).
"""

import pytest
from pydantic import ValidationError

from app.rag.models import (
    SOURCE_METADATA_FIELDS,
    Chunk,
    IndexResult,
    RagDocument,
    RetrievalResult,
)


def _document(**overrides) -> RagDocument:
    values = dict(
        document_id="kb-demo",
        title="Demo Knowledge",
        source="Test Handbook",
        topic="iot_testing",
        version="1.0",
        document_type="knowledge",
        text="Boundary values near the range edges must be tested.",
    )
    values.update(overrides)
    return RagDocument(**values)


def _chunk(**overrides) -> Chunk:
    values = dict(
        chunk_id="kb-demo--chunk-000",
        document_id="kb-demo",
        text="Boundary values near the range edges must be tested.",
        title="Demo Knowledge",
        source="Test Handbook",
        topic="iot_testing",
        version="1.0",
        document_type="knowledge",
        chunk_index=0,
        chunk_total=1,
    )
    values.update(overrides)
    return Chunk(**values)


def test_document_metadata_contains_all_source_fields():
    doc = _document()
    for field in SOURCE_METADATA_FIELDS:
        assert doc.metadata[field] == getattr(doc, field)


def test_document_defaults():
    doc = _document()
    assert doc.version == "1.0"
    assert doc.document_type == "knowledge"
    assert doc.source_path == ""


def test_document_frozen():
    with pytest.raises(ValidationError):
        _document().text = "changed"


def test_chunk_metadata_matches_document_metadata():
    doc = _document(document_id="kb-xyz", topic="boundary_value_analysis")
    chunk = _chunk(document_id="kb-xyz", topic="boundary_value_analysis")
    for key in SOURCE_METADATA_FIELDS:
        assert chunk.metadata[key] == doc.metadata[key]


def test_chunk_index_negative_rejected():
    with pytest.raises(ValidationError):
        _chunk(chunk_index=-1)


def test_chunk_total_zero_rejected():
    with pytest.raises(ValidationError):
        _chunk(chunk_total=0)


def test_chunk_frozen():
    with pytest.raises(ValidationError):
        _chunk().text = "changed"


def test_retrieval_result_relevance_bounds():
    _ = RetrievalResult(
        chunk_id="c",
        document_id="d",
        text="t",
        source="s",
        title="T",
        topic="x",
        metadata={"chunk_id": "c"},
        distance=0.25,
        relevance=0.75,
    )
    with pytest.raises(ValidationError):
        RetrievalResult(
            chunk_id="c",
            document_id="d",
            text="t",
            source="s",
            title="T",
            topic="x",
            metadata={"chunk_id": "c"},
            distance=0.25,
            relevance=1.5,
        )


def test_retrieval_result_frozen():
    result = RetrievalResult(
        chunk_id="c",
        document_id="d",
        text="t",
        source="s",
        title="T",
        topic="x",
        metadata={"chunk_id": "c"},
        distance=0.25,
        relevance=0.75,
    )
    with pytest.raises(ValidationError):
        result.text = "mutated"


def test_index_result_roundtrip_dict():
    result = IndexResult(
        collection="kb",
        document_count=2,
        chunk_count=5,
        skipped_duplicates=1,
        total_chunks=6,
        duration_seconds=0.12,
    )
    payload = result.model_dump()
    assert payload["chunk_count"] == 5
    assert IndexResult(**payload) == result