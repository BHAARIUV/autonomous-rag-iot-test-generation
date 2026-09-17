"""
Typed exceptions for the Phase 6 RAG knowledge-base subsystem.

WHAT:
    A small hierarchy of exceptions the RAG pipeline raises. Everything is a
    subclass of `RagError` so callers can catch one base type.

WHY:
    The rest of the framework (Phase 5 ingestion, future LLM generation) uses
    its own typed error hierarchies; the RAG subsystem needs the same clarity
    so that "query was blank", "embedding API unavailable" and "corpus file
    missing" are distinguishable instead of bubbling up bare ValueErrors.

HOW:
    Raise the most specific class; let callers catch `RagError` when they
    only need "something in RAG failed".

HOW TO VERIFY:
    See tests/unit/test_rag_* (each producer is expected to raise a typed
    subclass, never a bare exception).
"""

from __future__ import annotations


class RagError(Exception):
    """Base class for every error raised by the RAG subsystem."""


class KnowledgeBaseError(RagError):
    """Base for problems with the knowledge-corpus (documents) layer."""


class ManifestError(KnowledgeBaseError):
    """The corpus manifest is missing, malformed, or duplicates document ids."""


class DocumentLoadError(KnowledgeBaseError):
    """A document referenced by the manifest cannot be loaded or is invalid."""


class EmbeddingConfigurationError(RagError):
    """The configured embedding provider is invalid or unknown."""


class EmbeddingUnavailableError(RagError):
    """The embedding provider is configured but cannot currently produce
    embeddings (package missing, no API key, or the remote API failed)."""


class VectorStoreError(RagError):
    """The vector store cannot be opened, indexed, or queried."""


class InvalidQueryError(RagError):
    """Retrieval was called with a blank / malformed query."""


class IndexingError(RagError):
    """Indexing documents failed for a reason other than an unavailable
    embedding provider (e.g. embeddings and documents out of sync)."""