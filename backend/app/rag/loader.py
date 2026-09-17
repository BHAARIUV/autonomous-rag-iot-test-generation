"""
Load knowledge documents from the on-disk corpus.

WHAT:
    Reads a corpus directory containing a `manifest.json` plus one markdown/
    text file per document, and returns `RagDocument` values with their
    full source metadata.

WHY:
    The brief for Phase 6 requires the knowledge base to be project data
    (files under `knowledge_base/`), not hard-coded Python strings, with
    per-document metadata (document_id, title, source, topic, version,
    document_type). A JSON manifest gives us exactly that metadata without
    pulling in a YAML dependency.

HOW:
    `load_knowledge_base()` is the high-level entry point: it resolves the
    configured corpus directory (relative paths are resolved against the
    project root), reads `manifest.json`, validates it, then reads + parses
    each document file. Body text is parsed as Markdown-light: headings are
    kept as plain text.

HOW TO VERIFY:
    See tests/unit/test_rag_loader.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from app.config import PROJECT_ROOT, settings
from app.rag.errors import DocumentLoadError, ManifestError
from app.rag.models import RagDocument

MANIFEST_FILE_NAME = "manifest.json"
_MISSING_KEYS = ("document_id", "title", "source", "topic")

#: Allowed body text file extensions; anything else is refused with a clear error.
SUPPORTED_DOC_FORMATS = {".md", ".txt"}


def resolve_project_path(path: str | Path) -> Path:
    """Absolute path; relative ones are resolved against the project root."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _parse_body_text(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DocumentLoadError(
            f"Could not read document file '{path}': {exc}"
        ) from exc
    # Markdown-light: drop strongest emphasis characters but keep the words
    # so the metadata/body are clean for deterministic tokenization.
    for token in ("**", "__", "`", "# "):
        raw = raw.replace(token, "")
    return raw


def load_documents_from_dir(corpus_dir: str | Path) -> list[RagDocument]:
    """Load every document described by the corpus's manifest.json."""
    directory = resolve_project_path(corpus_dir)
    manifest_path = directory / MANIFEST_FILE_NAME
    if not manifest_path.exists():
        raise ManifestError(
            f"Corpus directory '{directory}' has no {MANIFEST_FILE_NAME}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"Manifest '{manifest_path}' is not valid JSON: {exc}"
        ) from exc

    entries = manifest.get("documents") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ManifestError(
            f"Manifest '{manifest_path}' has no 'documents' list"
        )

    by_id: dict[str, int] = {}
    documents: list[RagDocument] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ManifestError(
                f"Manifest entry {index} in '{manifest_path}' is not an object"
            )
        for key in _MISSING_KEYS:
            if not entry.get(key):
                raise ManifestError(
                    f"Manifest entry {index} in '{manifest_path}' is missing "
                    f"required key '{key}'"
                )
        document_id = str(entry["document_id"])
        if document_id in by_id:
            raise ManifestError(
                f"Manifest '{manifest_path}' defines document_id "
                f"'{document_id}' more than once"
            )
        by_id[document_id] = index

        file_name = entry.get("path")
        if not file_name:
            raise ManifestError(
                f"Manifest entry '{document_id}' has no 'path' to a document file"
            )
        doc_path = directory / file_name
        if doc_path.suffix.lower() not in SUPPORTED_DOC_FORMATS:
            raise ManifestError(
                f"Document file '{doc_path}' must be one of "
                f"{sorted(SUPPORTED_DOC_FORMATS)}"
            )
        if not doc_path.exists():
            raise DocumentLoadError(
                f"Document file '{doc_path}' (document_id '{document_id}') "
                "does not exist"
            )
        body = _parse_body_text(doc_path)
        documents.append(
            RagDocument(
                document_id=document_id,
                title=str(entry["title"]),
                source=str(entry["source"]),
                topic=str(entry["topic"]),
                version=str(entry.get("version") or "1.0"),
                document_type=str(entry.get("document_type") or "knowledge"),
                source_path=str(doc_path),
                text=body,
            )
        )
    logger.debug(
        f"Loaded {len(documents)} knowledge document(s) from "
        f"{directory}{' (empty corpus)' if not documents else ''}"
    )
    return documents


def load_knowledge_base(
    corpus_dir: str | Path | None = None,
    *,
    settings_=None,
) -> list[RagDocument]:
    """Load the configured knowledge base.

    If `corpus_dir` is None, `settings.rag_knowledge_dir` is used.
    """
    if corpus_dir is not None:
        directory: str | Path = corpus_dir
    else:
        cfg = settings_ if settings_ is not None else settings
        directory = cfg.rag_knowledge_dir
    return load_documents_from_dir(directory)