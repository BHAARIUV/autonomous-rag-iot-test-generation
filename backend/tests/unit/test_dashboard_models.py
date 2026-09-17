"""
Phase 12 — unit tests: dashboard imports, configuration, models, secret/API-key
protection, and mock-mode detection.
"""

from __future__ import annotations

from app.config import Settings
from app.dashboard import (
    DashboardService,
    models,
    provider,
    render,
    service,
)
from app.dashboard.models import not_available


class TestImports:
    def test_package_modules_importable(self):
        assert service.DashboardService is DashboardService
        assert hasattr(provider, "load_report")
        assert callable(render.render_html)
        assert callable(render.render_text)

    def test_dashboard_service_builds_with_default_config(self):
        svc = DashboardService()
        assert svc._cfg is not None


class TestConfig:
    def test_redacted_config_mock_mode(self):
        cfg = Settings(
            _env_file=None, LLM_PROVIDER="mock", LLM_MODEL="mock-llm",
            EMBEDDING_PROVIDER="local", EMBEDDING_DIMENSION=256,
        )
        red = provider.RedactedConfig(cfg)
        assert red.mock_mode is True
        assert red.has_api_key is False
        assert red.redacted_api_key() == "None (mock mode)"

    def test_redacted_config_never_exposes_secret(self):
        secret = "sk-SUPER-SECRET-12345"
        cfg = Settings(
            _env_file=None, LLM_PROVIDER="openai", LLM_MODEL="gpt-4o-mini",
            LLM_API_KEY=secret, EMBEDDING_PROVIDER="local",
            EMBEDDING_DIMENSION=256,
        )
        red = provider.RedactedConfig(cfg)
        # presence is reported, the value is never surfaced
        assert red.has_api_key is True
        assert red.mock_mode is False
        assert red.redacted_api_key() == "configured"
        assert secret not in red.redacted_api_key()

    def test_default_settings_are_mock(self):
        cfg = provider.default_settings()
        red = provider.RedactedConfig(cfg)
        assert red.mock_mode is True


class TestModelsDefaults:
    def test_not_available_marker(self):
        assert not_available() == "Not available"

    def test_overview_generation_mode_default(self):
        ov = models.OverviewView.__new__(models.OverviewView)
        assert models.OverviewView(project_name="p").generation_mode == "Not available"

    def test_fault_view_defaults(self):
        fv = models.FaultView(fault_id="F-1", fault_type="X")
        assert fv.detection_status == "Not available"
        assert fv.requirement_ids == []
        assert fv.detection_evidence == "Not available"

    def test_refinement_unavailable_default(self):
        rv = models.RefinementView()
        assert rv.available is False
        assert rv.iterations == []
