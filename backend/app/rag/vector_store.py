"""
ChromaDB-backed local vector store for the RAG subsystem.

WHAT:
    A thin, self-contained wrapper around ChromaDB that indexes `Chunk`
    values with their embeddings and answers similarity queries. Keeps the
    Chroma collection (a local, persistent, on-disk vector database) fully
    isolated from the rest of the framework.

WHY:
    The brief asks for a local vector database (ChromaDB preferred) with its
    own persistence directory, without touching the application database
    (`data/framework.db`). Chroma's PersistentClient writes to a directory
    of our choice (default `knowledge_base/chroma`, already in .gitignore).

HOW:
    All embedding vectors are supplied explicitly — the store never calls a
    downloading default embedding function, so indexing/retrieval work fully
    offline and deterministically in test mode. Duplicate chunk ids are
    detected against the collection's existing ids and skipped.

HOW TO VERIFY:
    See tests/unit/test_rag_vector_store.py.
"""

from __future__ import annotations

import time
from typing import Sequence

from loguru import logger

from app.rag.errors import VectorStoreError
from app.rag.models import AddChunksResult, Chunk, RetrievalResult

_DEFAULT_METADATA = {"hnsw:space": "cosine"}


class ChromaVectorStore:
    """Local ChromaDB vector store over a single collection."""

    def __init__(
        self,
        collection_name: str,
        persist_dir: str | None = None,
        *,
        ephemeral: bool = False,
    ):
        if len(collection_name or "") < 3:
            raise VectorStoreError(
                f"Chroma collection name {collection_name!r} must be at "
                "least 3 characters"
            )
        self._name = collection_name
        self._persist_dir = persist_dir
        self._client = None
        self._collection = None
        self._known_ids: set[str] | None = None
        self._ephemeral = ephemeral

    # ------------------------------------------------------------------ client

    def _ensure_client(self):
        if self._collection is not None:
            return
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings
            except ImportError as exc:  # pragma: no cover - chromadb is a hard dep
                raise VectorStoreError(
                    "ChromaDB is not installed; run `pip install chromadb`."
                ) from exc
            chroma_settings = ChromaSettings(anonymized_telemetry=False)
            if self._ephemeral or self._persist_dir is None:
                self._client = chromadb.EphemeralClient(settings=chroma_settings)
            else:
                from pathlib import Path

                Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=self._persist_dir, settings=chroma_settings
                )
        try:
            self._collection = self._client.get_or_create_collection(
                name=self._name, metadata=_DEFAULT_METADATA
            )
        except Exception:  # existing collection already present / metadata differs
            self._collection = self._client.get_collection(self._name)
        logger.debug(
            f"Vector store '{self._name}' ready "
            f"({('ephemeral' if self._ephemeral or self._persist_dir is None else self._persist_dir)})"
        )

    @property
    def collection(self):
        self._ensure_client()
        return self._collection

    # ------------------------------------------------------------------ state

    def count(self) -> int:
        self._ensure_client()
        return self.collection.count()

    def known_chunk_ids(self) -> set[str]:
        """Ids currently present in the collection (cached, refreshed on add)."""
        self._ensure_client()
        if self._known_ids is None:
            self._known_ids = set(self.collection.get(include=[])["ids"])
        return self._known_ids

    def document_ids(self) -> set[str]:
        """Distinct source document ids currently indexed."""
        self._ensure_client()
        metas = self.collection.get(include=["metadatas"])["metadatas"]
        return {meta.get("document_id", "") for meta in metas if meta}

    # ------------------------------------------------------------------ writes

    def add_chunks(
        self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]
    ) -> AddChunksResult:
        """Add chunks, skipping ids that already exist (idempotent).

        Raises IndexingError if chunk/embedding counts diverge.
        """
        self._ensure_client()
        if len(chunks) != len(embeddings):
            raise VectorStoreError(
                f"Got {len(chunks)} chunks but {len(embeddings)} embeddings"
            )
        if not chunks:
            return AddChunksResult(added=0, skipped_duplicates=0)

        existing = self.known_chunk_ids()
        seen = set(existing)
        to_add: list[tuple[Chunk, Sequence[float]]] = []
        skipped = 0
        for chunk, emb in zip(chunks, embeddings):
            if chunk.chunk_id in seen:
                skipped += 1
                continue
            seen.add(chunk.chunk_id)
            to_add.append((chunk, emb))
        if to_add:
            ids = [chunk.chunk_id for chunk, _ in to_add]
            docs = [chunk.text for chunk, _ in to_add]
            metas = [chunk.metadata for chunk, _ in to_add]
            vecs = [list(emb) for _, emb in to_add]
            self.collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
            self._known_ids = existing | set(ids)
        if skipped:
            logger.debug(f"Vector store skipped {skipped} duplicate chunk(s)")
        return AddChunksResult(added=len(to_add), skipped_duplicates=skipped)

    def clear(self) -> None:
        """Drop every chunk from the collection (used for rebuilds)."""
        self._ensure_client()
        try:
            self._client.delete_collection(self._name)
        except Exception as exc:
            try:
                still_present = self.count() > 0
            except Exception:
                still_present = False
            if still_present:
                raise VectorStoreError(
                    f"Failed to clear vector store '{self._name}': {exc}"
                ) from exc
        self._collection = None
        self._known_ids = set()
        self._ensure_client()
        logger.debug(f"Vector store '{self._name}' cleared")

    def close(self) -> None:
        """Release the underlying client so the persistence dir can be removed."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            self._client = None
            self._collection = None
            self._known_ids = None

    # ------------------------------------------------------------------ reads

    def query(self, embedding: Sequence[float], top_k: int) -> list[RetrievalResult]:
        """Return the `top_k` most related chunks to `embedding` (nearest first).

        Distance is cosine distance (0 = identical; lower = more relevant).
        """
        self._ensure_client()
        if top_k < 1:
            raise VectorStoreError(f"top_k must be >= 1, got {top_k}")
        if self.count() == 0:
            return []
        start = time.monotonic()
        response = self.collection.query(
            query_embeddings=[list(embedding)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        ids = response["ids"][0]
        distances = response["distances"][0]
        documents = response["documents"][0]
        metadatas = response["metadatas"][0]

        results: list[RetrievalResult] = []
        for chunk_id, distance, text, meta in zip(
            ids, distances, documents, metadatas
        ):
            meta = dict(meta or {})
            relevance = max(0.0, min(1.0, 1.0 - float(distance)))
            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=meta.get("document_id", ""),
                    text=text or "",
                    source=meta.get("source", ""),
                    title=meta.get("title", ""),
                    topic=meta.get("topic", ""),
                    metadata=meta,
                    distance=float(distance),
                    relevance=relevance,
                )
            )
        logger.debug(
            f"Vector store query returned {len(results)} of top_k={top_k} "
            f"in {time.monotonic() - start:.3f}s"
        )
        return results