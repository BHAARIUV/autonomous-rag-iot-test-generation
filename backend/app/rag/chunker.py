"""
Deterministic, configurable chunking of knowledge documents.

WHAT:
    Splits a `RagDocument` into one or more `Chunk` values. Every chunk
    repeats the document's full source metadata so traceability is never
    lost during chunking.

WHY:
    The Phase 6 brief requires configurable chunking where each chunk
    preserves chunk_id, document_id, text and source metadata, and NO source
    information is lost. Determinism matters because the local test mode
    must reproduce the same chunk layout on every run.

HOW:
    Text is whitespace-collapsed, then split on word boundaries such that a
    chunk never exceeds `chunk_size` characters; consecutive chunks overlap
    by approximately `chunk_overlap` characters (word-aligned). Empty text
    produces zero chunks.

HOW TO VERIFY:
    See tests/unit/test_rag_chunker.py.
"""

from __future__ import annotations

from loguru import logger

from app.rag.models import Chunk, RagDocument


def _tail_window(words: list[str], overlap: int) -> str:
    """Last words (in order) whose total length is about `overlap` chars."""
    acc: list[str] = []
    size = 0
    for word in reversed(words):
        cost = len(word) + (1 if acc else 0)
        if acc and size + cost > overlap:
            break
        if not acc and size + cost > overlap:  # single word longer than budget
            break
        acc.insert(0, word)
        size += cost
    return " ".join(acc)


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split raw text into word-boundary chunks of <= `chunk_size` chars.

    Overlapping windows are word-aligned, so pieces are never torn mid-word.
    """
    collapsed = " ".join(text.split())
    if not collapsed:
        return []
    if chunk_size < 1:
        chunk_size = 1
    if overlap < 0:
        overlap = 0

    words = collapsed.split(" ")
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for index, word in enumerate(words):
        cost = len(word) + (1 if current else 0)
        if current and size + cost > chunk_size:
            chunks.append(" ".join(current))
            seed = _tail_window(words[:index], overlap)
            current = seed.split(" ") if seed else []
            size = len(seed)
        if current:
            size += len(word) + 1
        else:
            size = len(word)
        current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_document(
    document: RagDocument,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """Chunk one document, attaching full source metadata to each chunk."""
    pieces = chunk_text(document.text, chunk_size, overlap)
    return [
        Chunk(
            chunk_id=f"{document.document_id}--chunk-{index:03d}",
            document_id=document.document_id,
            text=piece,
            title=document.title,
            source=document.source,
            topic=document.topic,
            version=document.version,
            document_type=document.document_type,
            chunk_index=index,
            chunk_total=len(pieces),
        )
        for index, piece in enumerate(pieces)
    ]


def chunk_documents(
    documents: list[RagDocument],
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """Chunk many documents; documents with empty text yield no chunks."""
    chunks: list[Chunk] = []
    skipped = 0
    for document in documents:
        if not document.text.strip():
            logger.debug(
                f"Skipping chunking of '{document.document_id}': empty text"
            )
            skipped += 1
            continue
        chunks.extend(chunk_document(document, chunk_size, overlap))
    if skipped:
        logger.debug(f"{skipped} empty document(s) produced no chunks")
    return chunks