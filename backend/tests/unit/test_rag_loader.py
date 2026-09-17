"""
Phase 6 unit tests: knowledge document loading — manifest parsing, validation,
metadata preservation, and the real shipped corpus.
"""

import json

import pytest

from app.config import PROJECT_ROOT
from app.rag.errors import DocumentLoadError, ManifestError
from app.rag.loader import (
    load_documents_from_dir,
    load_knowledge_base,
    resolve_project_path,
)

EXPECTED_TOPICS = {
    "iot_testing",
    "mqtt_testing",
    "temperature_sensor_testing",
    "boundary_value_analysis",
    "equivalence_partitioning",
    "negative_testing",
    "data_validation",
    "timing_sampling",
    "communication_reliability",
    "fault_injection",
    "device_offline_recovery",
    "sensor_accuracy",
}


def test_resolve_project_path_raises_relative_to_project_root():
    assert resolve_project_path("knowledge_base/documents") == (
        PROJECT_ROOT / "knowledge_base" / "documents"
    )
    assert resolve_project_path("x").is_absolute()


def test_load_shipped_corpus_has_twelve_documents():
    docs = load_knowledge_base()
    assert len(docs) == 12
    ids = [d.document_id for d in docs]
    assert len(set(ids)) == len(ids)


def test_shipped_corpus_metadata_complete():
    docs = load_knowledge_base()
    for doc in docs:
        assert doc.document_id.startswith("kb-")
        assert doc.title and doc.source and doc.topic and doc.version
        assert doc.document_type == "knowledge"
        assert doc.source_path.endswith(".md")
        assert doc.text.strip()


def test_shipped_corpus_covers_all_required_topics():
    topics = {d.topic for d in load_knowledge_base()}
    assert EXPECTED_TOPICS.issubset(topics)


def _write_corpus(tmp_path, entry, body="say something useful\n"):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manifest.json").write_text(
        json.dumps({"documents": [entry]}), encoding="utf-8"
    )
    if entry.get("path"):
        (docs / entry["path"]).write_text(body, encoding="utf-8")
    return docs


def test_load_documents_from_dir(tmp_path):
    docs_dir = _write_corpus(
        tmp_path,
        {
            "document_id": "kb-a",
            "title": "Alpha",
            "source": "Handbook",
            "topic": "negative_testing",
            "version": "2.1",
            "path": "a.md",
        },
    )
    docs = load_documents_from_dir(docs_dir)
    assert len(docs) == 1
    assert docs[0].document_id == "kb-a"
    assert docs[0].version == "2.1"
    assert docs[0].text == "say something useful\n"


def test_manifest_missing_raises(tmp_path):
    with pytest.raises(ManifestError):
        load_documents_from_dir(tmp_path)


def test_manifest_invalid_json_raises(tmp_path):
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_documents_from_dir(tmp_path)


def test_manifest_no_documents_list_raises(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"documents": []}), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_documents_from_dir(tmp_path)


def test_manifest_entry_missing_key_raises(tmp_path):
    docs = _write_corpus(
        tmp_path, {"document_id": "kb-a", "title": "A", "path": "a.md"}
    )  # missing 'source' and 'topic'
    with pytest.raises(ManifestError):
        load_documents_from_dir(docs)


def test_manifest_duplicate_document_id_raises(tmp_path):
    entry = {
        "document_id": "kb-a",
        "title": "A",
        "source": "S",
        "topic": "iot_testing",
        "path": "a.md",
    }
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manifest.json").write_text(
        json.dumps({"documents": [entry, entry]}), encoding="utf-8"
    )
    (docs / "a.md").write_text("text", encoding="utf-8")
    with pytest.raises(ManifestError):
        load_documents_from_dir(docs)


def test_manifest_entry_missing_path_raises(tmp_path):
    docs = _write_corpus(
        tmp_path,
        {
            "document_id": "kb-a",
            "title": "A",
            "source": "S",
            "topic": "iot_testing",
        },
    )
    with pytest.raises(ManifestError):
        load_documents_from_dir(docs)


def test_document_file_missing_raises(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manifest.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "document_id": "kb-a",
                        "title": "A",
                        "source": "S",
                        "topic": "iot_testing",
                        "path": "does_not_exist.md",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(DocumentLoadError):
        load_documents_from_dir(docs)


def test_unsupported_extension_raises(tmp_path):
    docs = _write_corpus(
        tmp_path,
        {
            "document_id": "kb-a",
            "title": "A",
            "source": "S",
            "topic": "iot_testing",
            "path": "a.bin",
        },
    )
    with pytest.raises(ManifestError):
        load_documents_from_dir(docs)


def test_empty_document_text_is_allowed(tmp_path):
    docs = _write_corpus(
        tmp_path,
        {
            "document_id": "kb-a",
            "title": "A",
            "source": "S",
            "topic": "iot_testing",
            "path": "a.md",
        },
        body="",
    )
    docs = load_documents_from_dir(docs)
    assert docs[0].text == ""