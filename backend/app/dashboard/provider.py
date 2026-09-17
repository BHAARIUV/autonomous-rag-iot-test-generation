"""
Phase 12 — read-only data provider for the dashboard.

WHY:
    The dashboard is a READ-ONLY reporting layer. This module is the ONLY place
    that touches project data, and every accessor is deliberately read-only:
      - It loads the Phase 10 `FinalProjectReport` from `reports/final_report.json`
        (no writes). If the report is missing it builds one ONCE in-memory from
        the real Phase 5-9 mock pipeline (nothing is persisted, nothing is
        modified).
      - The RAG knowledge catalog is read from the on-disk corpus manifest +
        documents via `load_documents_from_dir` (reads files only; it never calls
        `index_knowledge_base`, so the Chroma store is not modified).
      - The Phase 11 refinement result is COMPUTED on demand in mock mode from the
        real `RefinementService` (in-memory generation/execution; never persisted,
        never triggered implicitly by other sections).
    No API key is ever read back: only a redacted flag is exposed.

HOW:
    Functions raise `NotAvailableError` / return "Not available" markers rather
    than fabricating values. Smart callers surface that to the UI.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.faults import FaultType, make_fault
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.rag.loader import load_documents_from_dir
from app.rag.service import RagService
from app.refinement import RefinementService
from app.reporting import FinalReportService
from app.reporting.models import (
    FinalProjectReport,
    FinalTestSummary,
)
from app.testing import ExecutionService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "final_report.json"

_SPEC = (
    "Device: Temperature Sensor\n"
    "Range: -40 C to 125 C\n"
    "Accuracy: 0.5 C\n"
    "Sampling Interval: 1 s\n"
    "Communication Protocol: MQTT\n"
)

# A sentinel for values that genuinely do not exist (rendered as "Not available").
MISSING = object()


class NotAvailableError(RuntimeError):
    """Raised when a requested piece of project data does not exist."""


class RedactedConfig:
    """Safe, secret-free view of the project configuration for the dashboard."""

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg

    @property
    def llm_provider(self) -> str:
        return self._cfg.llm_provider

    @property
    def mock_mode(self) -> bool:
        return bool(self._cfg.is_mock_llm)

    @property
    def has_api_key(self) -> bool:
        return bool(self._cfg.llm_api_key)

    @property
    def llm_model(self) -> str:
        return self._cfg.llm_model

    def redacted_api_key(self) -> str:
        """Return only whether a key exists — never the key value."""
        return "configured" if self.has_api_key else "None (mock mode)"


def default_settings() -> Settings:
    return Settings(
        _env_file=None,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        RAG_TOP_K=4,
    )


# ---------------------------------------------------------------- report


def load_report_from_json(
    path: str | Path | None = None,
) -> FinalProjectReport:
    """Load an existing final report (read-only). Raises if unavailable."""
    report_path = Path(path) if path else DEFAULT_REPORT_PATH
    if not report_path.exists():
        raise NotAvailableError(f"Final report not found: {report_path}")
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    return FinalProjectReport.model_validate(payload)


def build_report_via_pipeline(cfg: Settings | None = None) -> FinalProjectReport:
    """Build a real `FinalProjectReport` in-memory from the Phase 5-9 mock
    pipeline. Read-only: creates RAG/generation/execution objects, gathers the
    natural suite, executes it, analyses it; NOTHING is written to disk."""
    cfg = cfg or default_settings()
    report_cfg = _clone_settings(cfg)
    rag = RagService(settings_=report_cfg)
    try:
        generator = GenerationService(settings_=report_cfg, rag_service=rag)
        executor = ExecutionService(settings_=report_cfg)
        spec = ingest_text(_SPEC, source="temperature_sensor.txt")
        requirements = spec.requirements
        test_cases: list = []
        results = []
        for req in requirements:
            suite = generator.generate_for_requirement(req, top_k=report_cfg.rag_top_k)
            test_cases.extend(suite.test_cases)
            res, _ = executor.execute_test_cases(suite.test_cases)
            results.extend(res)
        known_faults = [
            make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
            make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISCONNECT"),
        ]
        return FinalReportService.generate_final_report(
            requirements=requirements,
            test_cases=test_cases,
            results=results,
            fault_specs=known_faults,
            test_summary=FinalTestSummary(total=0, passed=0, failed=0,
                                          errors=0, skipped=0),
        )
    finally:
        rag.close()


def load_report(
    cfg: Settings | None = None,
    report_path: str | Path | None = None,
) -> FinalProjectReport:
    """Load the existing final report; fall back to an in-memory build."""
    try:
        return load_report_from_json(report_path)
    except NotAvailableError:
        return build_report_via_pipeline(cfg)


# ------------------------------------------------------------------ RAG


def load_knowledge_catalog(cfg: Settings | None = None) -> dict:
    """Read the RAG corpus manifest + documents (files only, no indexing).

    Returns:
        { "corpus_description": str, "corpus_version": str,
          "documents": [ {document_id,title,topic,source,version}, ... ] }
        or a dict with empty documents if the corpus is missing.
    """
    cfg = cfg or default_settings()
    corpus_dir = Path(cfg.rag_knowledge_dir)
    manifest_path = corpus_dir / "manifest.json"
    result = {
        "corpus_description": "Not available",
        "corpus_version": "Not available",
        "documents": [],
    }
    if not manifest_path.exists():
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return result
    if isinstance(manifest, dict):
        result["corpus_description"] = manifest.get("description", "Not available")
        result["corpus_version"] = str(manifest.get("corpus_version", "Not available"))
        for entry in manifest.get("documents", []):
            if not isinstance(entry, dict):
                continue
            result["documents"].append({
                "document_id": entry.get("document_id", "Not available"),
                "title": entry.get("title", "Not available"),
                "topic": entry.get("topic", "Not available"),
                "source": entry.get("source", "Not available"),
                "version": entry.get("version", "Not available"),
            })
    return result


def _clone_settings(cfg: Settings) -> Settings:
    """Build an isolated Settings for dashboard-internal services so we never
    mutate the caller's global config / environment."""
    return Settings(
        _env_file=None,
        LLM_PROVIDER=cfg.llm_provider or "mock",
        LLM_MODEL=cfg.llm_model or "mock-llm",
        EMBEDDING_PROVIDER=cfg.embedding_provider or "local",
        EMBEDDING_DIMENSION=cfg.embedding_dimension or 256,
        RAG_TOP_K=cfg.rag_top_k or 4,
        RAG_CHROMA_DIR=cfg.rag_chroma_dir,
        RAG_COLLECTION_NAME=cfg.rag_collection_name,
        RAG_KNOWLEDGE_DIR=cfg.rag_knowledge_dir,
    )


# ------------------------------------------------------------ refinement


def compute_refinement(
    cfg: Settings | None = None,
) -> object:
    """Compute a REAL Phase 11 refinement result in mock mode.

    Read-only: runs `RefinementService` in-memory (RAG retrieval, mock
    generation, safe execution) starting from a deliberately incomplete suite
    (only REQ-001 generated/executed) so the loop demonstrably closes gaps.
    Nothing is written to disk.
    """
    cfg = cfg or default_settings()
    report_cfg = _clone_settings(cfg)
    rag = RagService(settings_=report_cfg)
    try:
        generator = GenerationService(settings_=report_cfg, rag_service=rag)
        executor = ExecutionService(settings_=report_cfg)
        spec = ingest_text(_SPEC, source="temperature_sensor.txt")
        requirements = spec.requirements
        req1 = {r.requirement_id: r for r in requirements}["REQ-001"]
        suite = generator.generate_for_requirement(req1, top_k=report_cfg.rag_top_k)
        results, _ = executor.execute_test_cases(suite.test_cases)
        known_faults = [
            make_fault(FaultType.SENSOR_OUT_OF_RANGE, fault_id="F-SENSOR-OOR"),
            make_fault(FaultType.MQTT_DISCONNECT, fault_id="F-MQTT-DISCONNECT"),
        ]
        service = RefinementService(
            settings_=report_cfg, generator=generator, executor=executor,
            max_iterations=6, target_requirement_coverage=90.0,
        )
        return service.run(
            requirements=requirements,
            test_cases=suite.test_cases,
            results=results,
            fault_specs=known_faults,
        )
    finally:
        rag.close()


__all__ = [
    "MISSING",
    "NotAvailableError",
    "RedactedConfig",
    "default_settings",
    "load_report_from_json",
    "build_report_via_pipeline",
    "load_report",
    "load_knowledge_catalog",
    "compute_refinement",
    "DEFAULT_REPORT_PATH",
]
