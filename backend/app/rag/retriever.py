"""
Retrieval for the RAG subsystem.

WHAT:
    `Retriever` turns a natural-language query (or a Phase 5 requirement)
    into the most relevant knowledge chunks from the vector store, using an
    `EmbeddingProvider` to encode the query.

WHY:
    The brief requires a clean retriever interface: query text in, a
    structured list of `RetrievalResult` values out (chunk_id, document_id,
    text, source, metadata, distance + relevance), with configurable top_k.
    Retrieval never fabricates content — it only returns indexed chunks.

HOW:
    `retrieve()` validates the query (blank / bad top_k rejected with a
    typed error), embeds it, then delegates to the vector store.

HOW TO VERIFY:
    See tests/unit/test_rag_retriever.py and
    tests/integration/test_rag_retrieval.py.
"""

from __future__ import annotations

import time

from loguru import logger

from app.rag.embeddings import EmbeddingProvider
from app.rag.errors import InvalidQueryError, VectorStoreError
from app.rag.models import RetrievalResult


class Retriever:
    """Embeds a query and fetches relevant chunks from a vector store."""

    def __init__(
        self,
        vector_store,
        embedding_provider: EmbeddingProvider,
        default_top_k: int = 4,
    ):
        self._store = vector_store
        self._embeddings = embedding_provider
        self._default_top_k = max(1, int(default_top_k))

    def retrieve(
        self,
        query_text: str,
        top_k: int | None = None,
    ) -> list[RetrievalResult]:
        """Return the top_k most relevant chunks for `query_text`."""
        if not query_text or not query_text.strip():
            raise InvalidQueryError("Retrieval query must not be blank")
        k = self._default_top_k if top_k is None else int(top_k)
        if k < 1:
            raise InvalidQueryError(
                f"top_k must be >= 1, got {k}"
            )

        start = time.monotonic()
        query_embedding = self._embeddings.embed_query(query_text.strip())
        results = self._store.query(query_embedding, k)
        if len(results) > k:
            raise VectorStoreError(
                f"Vector store returned {len(results)} results for top_k={k}"
            )
        logger.debug(
            f"Retrieved {len(results)} chunk(s) for "
            f"{query_text[:60]!r} in {time.monotonic() - start:.3f}s"
        )
        return results