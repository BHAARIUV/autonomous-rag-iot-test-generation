"""
Phase 12 — integration smoke test.

Verifies the dashboard can load its REAL data end-to-end (report + RAG catalog +
Phase 11 refinement in mock mode) and that the demo can render + write the HTML
dashboard successfully. This is the "dashboard can start/load its data" check.
"""

from __future__ import annotations

from app.dashboard import provider, render
from app.dashboard.demo import run_demo
from app.dashboard.service import DashboardService


def test_dashboard_builds_full_data():
    data = DashboardService().build()
    # real sections populated
    assert data.overview.project_name
    assert data.overview.current_phase == 13  # Phases 1-13 complete; 14 NOT STARTED
    assert data.overview.completed_phases >= 13
    assert data.overview.generation_mode in {"MOCK", "REAL LLM"}
    assert data.requirements, "requirements section must populate"
    assert data.knowledge.document_count > 0
    assert data.final_status.phases
    # refinement is available when the mock loop runs successfully
    assert data.refinement.available is True
    assert data.refinement.stop_reason
    # traceability exposes real ids
    assert all(r.requirement_id for r in data.traceability.rows)


def test_dashboard_text_and_html_render():
    data = DashboardService().build()
    text = render.render_text(data)
    for section in ("REQUIREMENTS", "RAG / KNOWLEDGE", "TEST GENERATION",
                    "TEST EXECUTION", "FAULT ANALYSIS", "REFINEMENT",
                    "FINAL PROJECT STATUS"):
        assert section in text, f"missing section {section}"
    html = render.render_html(data)
    for section in ("A. Project Overview", "I. Final Project Status"):
        assert section in html
    # the generation mode is never hidden in the rendered output
    assert "MOCK" in html or "REAL LLM" in html


def test_demo_writes_dashboard_report(tmp_path):
    out = run_demo(print_summary=False)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "Project Overview" in content
    assert "Final Project Status" in content
