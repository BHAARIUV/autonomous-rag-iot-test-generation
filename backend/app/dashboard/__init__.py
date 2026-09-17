"""
Phase 12 — Dashboard.

A READ-ONLY visualization/reporting layer for the Autonomous RAG-Based IoT Test
Generation & Fault Detection Framework. It consumes REAL project data (the
Phase 10 final report, the RAG corpus manifest, and a real Phase 11 refinement
result computed on load in mock mode) and renders a lightweight, dependency-free
HTML dashboard.

WHY read-only:
    - It never executes generated code or arbitrary scripts.
    - It never modifies requirements, test cases, execution results, fault
      results, or the RAG database.
    - Refinement is only ever COMPUTED on demand for display (mock mode) — never
      persisted, and never triggered by viewing other sections.
    - API keys are never surfaced; only their presence (redacted) is shown.

HOW TO RUN:
    python -m app.dashboard        # serve the HTML over local http.server
    python -m app.dashboard.demo   # write reports/dashboard.html + print summary
"""

from app.dashboard import models, provider, render, service
from app.dashboard.service import DashboardService

__all__ = [
    "models",
    "provider",
    "render",
    "service",
    "DashboardService",
]
