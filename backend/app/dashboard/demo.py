"""
Phase 12 — dashboard demo (headless, no browser required).

Builds the dashboard's real data, writes `reports/dashboard.html` and prints a
plain-text summary to the console. Also used by the integration smoke test to
verify the dashboard can load its data successfully.

HOW TO RUN:
    python -m app.dashboard.demo
"""

from __future__ import annotations

from pathlib import Path

from app.dashboard import render
from app.dashboard.provider import PROJECT_ROOT
from app.dashboard.service import DashboardService


def run_demo(print_summary: bool = True) -> Path:
    service = DashboardService()
    data = service.build()
    html = render.render_html(data)
    text = render.render_text(data)

    out_dir = PROJECT_ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "dashboard.html"
    out_path.write_text(html, encoding="utf-8")

    if print_summary:
        print(text)
        print(f"\nHTML dashboard written to: {out_path}")
        print("Serve it with:  python -m app.dashboard")
    return out_path


if __name__ == "__main__":
    run_demo()
