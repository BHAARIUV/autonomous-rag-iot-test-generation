"""
Phase 6 unit tests: deterministic chunking — size limits, overlaps, metadata
preservation, empty handling, and determinism.
"""

import pytest

from app.rag.chunker import chunk_document, chunk_documents, chunk_text
from app.rag.models import RagDocument


def _doc(text, document_id="kb-d", topic="iot_testing") -> RagDocument:
    return RagDocument(
        document_id=document_id,
        title="Doc Title",
        source="Test Handbook",
        topic=topic,
        version="1.0",
        document_type="knowledge",
        text=text,
    )


def test_empty_text_yields_no_chunks():
    assert chunk_text("   ", 100, 20) == []
    assert chunk_text("", 100, 20) == []


def test_whitespace_collapsed_deterministic_example():
    text = "a b c d e f g h i j k l"
    chunks = chunk_text(text, chunk_size=5, overlap=2)
    assert chunks == ["a b c", "c d e", "e f g", "g h i", "i j k", "k l"]


def test_chunk_size_bound_respected():
    text = " ".join(f"word{i}" for i in range(200))
    chunk_size, overlap = 60, 10
    chunks = chunk_text(text, chunk_size, overlap)
    assert chunks
    max_word = max(len(w) for w in text.split())
    for piece in chunks:
        assert len(piece) <= chunk_size + overlap + max_word + 2


def test_chunk_document_structure_and_metadata():
    text = " ".join(f"term{i}" for i in range(300))
    doc = _doc(text, document_id="kb-abc", topic="fault_injection")
    chunks = chunk_document(doc, chunk_size=80, overlap=10)
    assert len(chunks) > 1
    for index, chunk in enumerate(chunks):
        assert chunk.chunk_id.startswith("kb-abc--chunk-")
        assert chunk.document_id == "kb-abc"
        assert chunk.chunk_index == index
        assert chunk.chunk_total == len(chunks)
        assert chunk.title == "Doc Title"
        assert chunk.source == "Test Handbook"
        assert chunk.topic == "fault_injection"
        assert chunk.metadata["document_id"] == "kb-abc"


def test_chunk_ids_unique():
    doc = _doc(" ".join(f"t{i}" for i in range(300)), document_id="kb-u")
    ids = [c.chunk_id for c in chunk_document(doc, chunk_size=80, overlap=10)]
    assert len(ids) == len(set(ids))


def test_single_chunk_document():
    doc = _doc("short text")
    chunks = chunk_document(doc, chunk_size=500, overlap=20)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].chunk_total == 1
    assert chunks[0].text == "short text"


def test_chunk_document_empty_text():
    assert chunk_document(_doc("   "), chunk_size=100, overlap=10) == []


def test_chunk_documents_skips_empty_but_keeps_others():
    docs = [
        _doc("first non-empty document", document_id="kb-1"),
        _doc("   ", document_id="kb-2"),
        _doc("third with unique boundary terms", document_id="kb-3"),
    ]
    chunks = chunk_documents(docs, chunk_size=200, overlap=10)
    assert len(chunks) == 2
    assert {c.document_id for c in chunks} == {"kb-1", "kb-3"}


def test_chunking_is_deterministic():
    text = ("Boundary Value Analysis tests plus-minus values near the edge of "
            "the declared temperature range from minus 40 to plus 125. ")
    a = chunk_text(text * 5, chunk_size=100, overlap=15)
    b = chunk_text(text * 5, chunk_size=100, overlap=15)
    assert a == b


def test_overlap_retains_context_between_chunks():
    text = " ".join(f"token{i}" for i in range(200))
    chunks = chunk_text(text, chunk_size=80, overlap=20)
    assert chunks
    # No token is lost across chunk boundaries ...
    assert set(text.split()) == set(w for c in chunks for w in c.split()) == {
        f"token{i}" for i in range(200)
    }
    # ... and overlap adds redundancy: total content exceeds the input length.
    assert sum(len(c.split()) for c in chunks) > len(text.split())
    # Every non-final chunk ends at the exact inject point of the next chunk.
    for prev, nxt in zip(chunks, chunks[1:]):
        first_nxt_word = nxt.split()[0]
        assert first_nxt_word in prev.split()


def test_chunk_size_one():
    assert chunk_text("a b", chunk_size=1, overlap=0) == ["a", "b"]