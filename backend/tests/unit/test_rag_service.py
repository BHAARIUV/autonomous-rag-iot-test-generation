"""
Phase 6 unit tests: RagService orchestration — indexing, idempotency, rebuild,
requirement-driven retrieval, invalid queries, and graceful provider failure.
"""

import pytest

from app.config import Settings
from app.ingestion.models import Constraint, Requirement, RequirementCategory
from app.rag.embeddings import EmbeddingProvider, HashingEmbeddingProvider
from app.rag.errors import EmbeddingUnavailableError, IndexingError, InvalidQueryError
from app.rag.models import RagDocument
from app.rag.service import RagService, requirement_query_text
from app.rag.vector_store import ChromaVectorStore


def _document(document_id="kb-a", body="Boundary edges of a temperature range must be tested.") -> RagDocument:
    return RagDocument(
        document_id=document_id,
        title="Doc",
        source="Handbook",
        topic="boundary_value_analysis",
        text=body,
    )


def _requirements_result() -> Requirement:
    return Requirement(
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


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path),
        RAG_COLLECTION_NAME="svc_kb",
        RAG_CHUNK_SIZE=80,
        RAG_CHUNK_OVERLAP=10,
        RAG_TOP_K=3,
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
    )


@pytest.fixture
def service(settings):
    svc = RagService(settings_=settings)
    yield svc
    svc.close()


def test_index_documents_result_fields(service):
    result = service.index_documents([_document()])
    assert result.document_count == 1
    assert result.chunk_count >= 1
    assert result.skipped_duplicates == 0
    assert result.total_chunks == result.chunk_count
    assert result.collection == "svc_kb"
    assert result.duration_seconds >= 0


def test_index_documents_is_idempotent(service):
    docs = [_document("kb-1"), _document("kb-2", body="MQTT publish subscribe QoS test guidance.")]
    first = service.index_documents(docs)
    second = service.index_documents(docs)
    assert second.chunk_count == 0
    assert second.skipped_duplicates == first.chunk_count
    assert second.total_chunks == first.total_chunks


def test_index_empty_documents_ok(service):
    result = service.index_documents([])
    assert result.document_count == 0
    assert result.chunk_count == 0
    assert result.total_chunks == 0


def test_index_empty_text_documents_produce_no_chunks(service):
    result = service.index_documents([_document("kb-empty", body="   ")])
    assert result.chunk_count == 0
    assert result.document_count == 1


def test_duplicate_documents_in_one_call_skip(service):
    doc = _document()
    first = service.index_documents([doc, doc])
    assert first.chunk_count >= 1
    assert first.skipped_duplicates == first.chunk_count


def test_rebuild_clears_then_reindexes(service):
    service.index_documents([_document()])
    result = service.index_documents([_document()], rebuild=True)
    assert result.skipped_duplicates == 0
    assert result.chunk_count >= 1
    assert service.store.count() == result.total_chunks


def test_retrieve_after_index(service):
    service.index_documents([_document()])
    results = service.retrieve("temperature range boundary edges", top_k=2)
    assert results
    assert results[0].document_id == "kb-a"


def test_retrieve_blank_query_raises(service):
    with pytest.raises(InvalidQueryError):
        service.retrieve("   ")


def test_retrieve_for_requirement_with_model(service):
    service.index_documents([_document()])
    req = _requirements_result()
    results = service.retrieve_for_requirement(req, top_k=2)
    assert results
    assert results[0].document_id == "kb-a"


def test_retrieve_for_requirement_with_string(service):
    service.index_documents([_document()])
    results = service.retrieve_for_requirement(
        "temperature between -40 and 125 boundary", top_k=2
    )
    assert results


def test_retrieve_for_requirement_invalid_type(service):
    with pytest.raises(InvalidQueryError):
        service.retrieve_for_requirement(42)


def test_requirement_query_text_contains_all_signal():
    req = _requirements_result()
    text = requirement_query_text(req)
    assert "REQ-001" in text
    assert "-40" in text and "125" in text
    assert "RANGE" in text
    assert "constraints" in text.lower()


def test_index_knowledge_base_real_corpus(service):
    result = service.index_knowledge_base()
    assert result.document_count == 12
    assert result.chunk_count == result.total_chunks
    assert result.chunk_count >= 12


def test_embedding_provider_unavailable_fails_gracefully(settings):
    class BrokenProvider(EmbeddingProvider):
        dimension = 256

        def embed_documents(self, texts):
            raise EmbeddingUnavailableError("embedding API down")

        def embed_query(self, text):
            raise EmbeddingUnavailableError("embedding API down")

    store = ChromaVectorStore("broken_kb", ephemeral=True)
    svc = RagService(settings_=settings, vector_store=store, embedding_provider=BrokenProvider())
    try:
        with pytest.raises(EmbeddingUnavailableError):
            svc.index_documents([_document()])
        with pytest.raises(EmbeddingUnavailableError):
            svc.retrieve("temperature")
    finally:
        svc.close()


def test_embedding_count_mismatch_raises(settings):
    class ShortProvider(HashingEmbeddingProvider):
        def embed_documents(self, texts):
            return super().embed_documents(texts)[:0]  # wrong count

    store = ChromaVectorStore("short_kb", ephemeral=True)
    svc = RagService(settings_=settings, vector_store=store, embedding_provider=ShortProvider(256))
    try:
        with pytest.raises(IndexingError):
            svc.index_documents([_document(), _document("kb-b")])
    finally:
        svc.close()


def test_settings_rag_defaults_present():
    cfg = Settings(_env_file=None)
    assert cfg.rag_chroma_dir == "knowledge_base/chroma"
    assert cfg.rag_knowledge_dir == "knowledge_base/documents"
    assert cfg.rag_collection_name == "iot_knowledge"
    assert cfg.rag_chunk_size > 0
    assert cfg.rag_top_k >= 1
    assert cfg.embedding_dimension >= 16