"""
Public orchestration for the Phase 6 RAG knowledge-base subsystem.

WHAT:
    `RagService` ties the pieces together:
        index_documents(...)            — chunk + embed + store documents
        index_knowledge_base(...)       — index the on-disk corpus
        retrieve(...)                   — query for relevant knowledge
        retrieve_for_requirement(...)   — same, driven by a Phase 5 Requirement
        rebuild(...)                    — clear the index and re-index
    Plus module-level convenience functions that operate on the default
    configured knowledge base (see `DefaultService`).

WHY:
    Phase 7's LLM test generator will call `retrieve_for_requirement(...)`
    to obtain context for a Phase 5 requirement, so the interface must be
    small, explicit, Phase-5-compatible, and honest: retrieval returns only
    indexed knowledge chunks — it never fabricates content.

HOW:
    All operations log via loguru and fail with typed RagError subclasses
    (e.g. `InvalidQueryError` for blank queries, `EmbeddingUnavailableError`
    when a real embedding provider is configured but unusable).

HOW TO VERIFY:
    See tests/unit/test_rag_service.py and
    tests/integration/test_rag_retrieval.py.
"""

from __future__ import annotations

import time
from typing import Iterable

from loguru import logger

from app.rag.chunker import chunk_documents
from app.rag.embeddings import EmbeddingProvider, create_embedding_provider
from app.rag.errors import IndexingError, InvalidQueryError
from app.rag.loader import load_knowledge_base
from app.rag.models import IndexResult, RagDocument, RetrievalResult
from app.rag.retriever import Retriever
from app.rag.vector_store import ChromaVectorStore


def requirement_query_text(requirement) -> str:
    """Build a retrieval query string from a Phase 5 `Requirement`.

    Combines the requirement id, description, category and constraints so
    the embedding has rich signal to match against the knowledge corpus.
    """
    parts = [
        f"{requirement.requirement_id}: {requirement.description}",
        f"Category: {requirement.category.value}"
        if requirement.category is not None
        else "",
    ]
    constraints = [
        " ".join(part for part in (c.kind, c.value, c.unit or "") if part)
        for c in requirement.constraints
    ]
    if constraints:
        parts.append("Constraints: " + ", ".join(constraints))
    return " ".join(part for part in parts if part)


class RagService:
    """End-to-end RAG service: index documents, retrieve relevant knowledge."""

    def __init__(
        self,
        *,
        vector_store=None,
        embedding_provider: EmbeddingProvider | None = None,
        settings_=None,
        knowledge_dir: str | None = None,
    ):
        from app.config import settings as _singleton

        self._settings = settings_ if settings_ is not None else _singleton
        self._knowledge_dir = knowledge_dir
        self._embedding_provider = embedding_provider or create_embedding_provider(
            settings_=self._settings
        )
        if vector_store is not None:
            self._store = vector_store
        else:
            self._store = ChromaVectorStore(
                collection_name=self._settings.rag_collection_name,
                persist_dir=self._settings.rag_chroma_dir,
            )
        self._retriever = Retriever(
            vector_store=self._store,
            embedding_provider=self._embedding_provider,
            default_top_k=self._settings.rag_top_k,
        )

    # ------------------------------------------------------------------ indexing

    def index_documents(
        self,
        documents: Iterable[RagDocument],
        *,
        rebuild: bool = False,
    ) -> IndexResult:
        """Chunk, embed and index documents. Idempotent and rebuild-friendly."""
        docs = list(documents)
        if rebuild:
            logger.info("Rebuilding index: clearing vector store")
            self._store.clear()

        start = time.monotonic()
        chunks = chunk_documents(
            docs,
            chunk_size=self._settings.rag_chunk_size,
            overlap=self._settings.rag_chunk_overlap,
        )
        if not chunks:
            result = IndexResult(
                collection=self._settings.rag_collection_name,
                document_count=len(docs),
                chunk_count=0,
                skipped_duplicates=0,
                total_chunks=self._store.count(),
                duration_seconds=time.monotonic() - start,
            )
            logger.info(
                f"Indexed {len(docs)} document(s), 0 chunk(s) "
                f"({result.collection})"
            )
            return result

        embeddings = self._embedding_provider.embed_documents(
            [chunk.text for chunk in chunks]
        )
        if len(embeddings) != len(chunks):
            raise IndexingError(
                f"Embedding provider returned {len(embeddings)} vectors for "
                f"{len(chunks)} chunks"
            )
        added = self._store.add_chunks(chunks, embeddings)
        result = IndexResult(
            collection=self._settings.rag_collection_name,
            document_count=len(docs),
            chunk_count=added.added,
            skipped_duplicates=added.skipped_duplicates,
            total_chunks=self._store.count(),
            duration_seconds=time.monotonic() - start,
        )
        logger.info(
            f"Indexed {result.document_count} document(s) -> "
            f"{result.chunk_count} new chunk(s), "
            f"{result.skipped_duplicates} duplicate(s) skipped "
            f"({result.collection}, {result.total_chunks} total, "
            f"{result.duration_seconds:.3f}s)"
        )
        return result

    def index_knowledge_base(self, *, rebuild: bool = False) -> IndexResult:
        """Index the on-disk knowledge corpus."""
        docs = load_knowledge_base(self._knowledge_dir, settings_=self._settings)
        return self.index_documents(docs, rebuild=rebuild)

    def rebuild(self) -> IndexResult:
        """Convenience: clear the store and re-index the knowledge base."""
        return self.index_knowledge_base(rebuild=True)

    # ------------------------------------------------------------------ retrieval

    def retrieve(
        self,
        query_text: str,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve the most relevant knowledge chunks for a query string."""
        return self._retriever.retrieve(query_text, top_k=top_k)

    def retrieve_for_requirement(
        self,
        requirement,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant knowledge for a Phase 5 requirement.

        Accepts an `app.ingestion.models.Requirement` or a plain string.
        """
        if isinstance(requirement, str):
            query_text = requirement
        elif hasattr(requirement, "requirement_id") and hasattr(
            requirement, "description"
        ):
            query_text = requirement_query_text(requirement)
        else:
            raise InvalidQueryError(
                "retrieve_for_requirement expects a Requirement or a query string"
            )
        logger.debug(
            f"Retrieving knowledge for requirement {query_text[:80]!r}"
        )
        return self._retriever.retrieve(query_text, top_k=top_k)

    # ------------------------------------------------------------------ lifecycle

    def close(self) -> None:
        """Release Chroma resources (call when done with a service)."""
        self._store.close()

    @property
    def store(self):
        """Expose the underlying vector store for introspection (tests, stats)."""
        return self._store


# ---------------------------------------------------------------------------
# Module-level convenience API operating on the default configured knowledge base
# ---------------------------------------------------------------------------

_DEFAULT_SERVICE: RagService | None = None


def get_default_service() -> RagService:
    """Lazily-built shared `RagService` using project configuration."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = RagService()
    return _DEFAULT_SERVICE


def reset_default_service() -> None:
    """Drop the cached default service (used by tests to avoid stale state)."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is not None:
        _DEFAULT_SERVICE.close()
        _DEFAULT_SERVICE = None


def index_knowledge_base(*, rebuild: bool = False) -> IndexResult:
    """Index the configured knowledge base (idempotent; rebuild to refresh)."""
    return get_default_service().index_knowledge_base(rebuild=rebuild)


def retrieve(query_text: str, top_k: int | None = None) -> list[RetrievalResult]:
    """Retrieve relevant knowledge chunks for a natural-language query."""
    return get_default_service().retrieve(query_text, top_k=top_k)


def retrieve_for_requirement(
    requirement, top_k: int | None = None
) -> list[RetrievalResult]:
    """Retrieve relevant knowledge for a Phase 5 `Requirement` or query string."""
    return get_default_service().retrieve_for_requirement(requirement, top_k=top_k)


def index_documents(
    documents: Iterable[RagDocument], *, rebuild: bool = False
) -> IndexResult:
    """Index an explicit list of documents via the default service."""
    return get_default_service().index_documents(documents, rebuild=rebuild)