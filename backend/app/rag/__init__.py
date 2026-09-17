"""
Phase 6 — RAG Knowledge Base and Retrieval.

WHAT:
    A local, offline-capable RAG knowledge-base subsystem: it loads a
    knowledge corpus of IoT testing documents, chunks them deterministically,
    embeds them (local hashing provider by default; OpenAI provider optional),
    indexes the vectors in a local ChromaDB vector store, and retrieves the
    most relevant knowledge for a query or a Phase 5 requirement.

WHY:
    Phase 7 (LLM test generation) consumes the retrieved knowledge as context.
    Phase 6 must NOT generate tests itself — it only indexes and retrieves.

HOW:
    Data flows
        knowledge documents -> loader -> chunker -> embeddings -> vector
        store -> retriever -> relevant context
    The knowledge corpus lives as data files under `knowledge_base/` with a
    JSON manifest carrying source metadata. Everything is configurable via
    `app/config.py` / `.env` (RAG_*, EMBEDDING_*).

HOW TO VERIFY:
    - `venv\\Scripts\\python.exe -m pytest tests/unit/test_rag_* -q`
    - `venv\\Scripts\\python.exe -m pytest tests/integration/test_rag_retrieval.py -q`
    - Run with the default corpus:
        python -c "from app.rag import index_knowledge_base, retrieve_for_requirement
                   index_knowledge_base(); print(retrieve_for_requirement('REQ-001: Temperature must stay between -40 C and 125 C.'))"
"""

from app.rag.errors import (
    DocumentLoadError,
    EmbeddingConfigurationError,
    EmbeddingUnavailableError,
    IndexingError,
    InvalidQueryError,
    KnowledgeBaseError,
    ManifestError,
    RagError,
    VectorStoreError,
)
from app.rag.models import (
    Chunk,
    IndexResult,
    RagDocument,
    RetrievalResult,
    SOURCE_METADATA_FIELDS,
)
from app.rag.chunker import chunk_document, chunk_documents, chunk_text
from app.rag.embeddings import (
    EmbeddingProvider,
    HashingEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)
from app.rag.loader import (
    load_documents_from_dir,
    load_knowledge_base,
    resolve_project_path,
)
from app.rag.retriever import Retriever
from app.rag.service import (
    RagService,
    get_default_service,
    index_documents,
    index_knowledge_base,
    requirement_query_text,
    reset_default_service,
    retrieve,
    retrieve_for_requirement,
)
from app.rag.vector_store import ChromaVectorStore

__all__ = [
    # errors
    "RagError",
    "KnowledgeBaseError",
    "ManifestError",
    "DocumentLoadError",
    "EmbeddingConfigurationError",
    "EmbeddingUnavailableError",
    "VectorStoreError",
    "InvalidQueryError",
    "IndexingError",
    # models
    "RagDocument",
    "Chunk",
    "RetrievalResult",
    "IndexResult",
    "SOURCE_METADATA_FIELDS",
    # loading / chunking
    "load_knowledge_base",
    "load_documents_from_dir",
    "resolve_project_path",
    "chunk_document",
    "chunk_documents",
    "chunk_text",
    # embeddings
    "EmbeddingProvider",
    "HashingEmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "create_embedding_provider",
    # vector store / retriever
    "ChromaVectorStore",
    "Retriever",
    # service
    "RagService",
    "requirement_query_text",
    "get_default_service",
    "reset_default_service",
    "index_documents",
    "index_knowledge_base",
    "retrieve",
    "retrieve_for_requirement",
]