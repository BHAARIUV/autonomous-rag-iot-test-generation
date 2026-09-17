"""
Structured data model of the Phase 6 RAG knowledge-base subsystem.

WHAT:
    Pydantic models for every object that crosses the RAG pipeline:
    - `RagDocument`: one knowledge-base source document plus its metadata.
    - `Chunk`: one indexed piece of a document, carrying the full source
      metadata so traceability survives chunking.
    - `RetrievalResult`: one knowledge chunk returned by a retrieval call,
      with the relevance/distance score.
    - `IndexResult`: a summary of an indexing run.

WHY:
    Mirroring the Phase 5 ingestion approach (frozen pydantic models) keeps
    the data contracts explicit and serializable, and makes "source came
    from document X, chunk Y" verifiable at every pipeline stage.

HOW:
    Models are frozen where they represent an immutable record (built once,
    never mutated), matching `app/ingestion/models.py` and `app/faults/models.py`.

HOW TO VERIFY:
    See tests/unit/test_rag_models.py.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

SOURCE_METADATA_FIELDS = (
    "document_id",
    "title",
    "source",
    "topic",
    "version",
    "document_type",
)


class RagDocument(BaseModel):
    """A single source knowledge document, with required metadata."""

    model_config = {"frozen": True}

    document_id: str = Field(description="Unique id, e.g. kb-iot-fundamentals")
    title: str
    source: str = Field(description="Human-readable provenance, e.g. 'IoT Testing Handbook'")
    topic: str = Field(description="One of the corpus topic labels (e.g. boundary_value_analysis)")
    version: str = "1.0"
    document_type: str = "knowledge"
    source_path: str = Field(
        default="", description="File path the document was loaded from (empty for manual)"
    )
    text: str = Field(description="The document's full body text")

    @property
    def metadata(self) -> dict[str, str]:
        """The source-traceability metadata attached to every chunk."""
        return {
            "document_id": self.document_id,
            "title": self.title,
            "source": self.source,
            "topic": self.topic,
            "version": self.version,
            "document_type": self.document_type,
        }


class Chunk(BaseModel):
    """One indexed piece of a document; source metadata is preserved."""

    model_config = {"frozen": True}

    chunk_id: str = Field(description="Unique id, e.g. kb-iot-fundamentals--chunk-000")
    document_id: str
    text: str
    title: str
    source: str
    topic: str
    version: str
    document_type: str
    chunk_index: int = Field(ge=0, description="0-based position within the document")
    chunk_total: int = Field(ge=1, description="Number of chunks the document produced")

    @property
    def metadata(self) -> dict[str, str]:
        """Source metadata attached to this chunk (used as Chroma metadata)."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "title": self.title,
            "source": self.source,
            "topic": self.topic,
            "version": self.version,
            "document_type": self.document_type,
        }


class RetrievalResult(BaseModel):
    """One knowledge chunk returned by a retrieval query."""

    model_config = {"frozen": True}

    chunk_id: str
    document_id: str
    text: str
    source: str
    title: str
    topic: str
    metadata: dict[str, str] = Field(
        description="Full chunk metadata (chunk_id, document_id, title, source, topic, version, document_type)"
    )
    distance: float = Field(
        description="Vector distance from the query (lower = more relevant; cosine space, 0 = identical)"
    )
    relevance: float = Field(
        ge=0.0,
        le=1.0,
        description="1 - distance, clamped to [0, 1]; 1 = most relevant",
    )


class IndexResult(BaseModel):
    """Summary of one indexing run."""

    collection: str
    document_count: int
    chunk_count: int = Field(description="Chunks newly added by this run")
    skipped_duplicates: int = Field(description="Chunks already present and left untouched")
    total_chunks: int = Field(description="Chunks in the collection after this run")
    duration_seconds: float


class AddChunksResult(BaseModel):
    """Low-level result of adding chunks to the vector store."""

    added: int
    skipped_duplicates: int