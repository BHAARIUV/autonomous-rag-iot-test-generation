"""
Phase 15 — one-way JSON data dump for the React frontend (read-only).

WHY:
    The existing backend dashboard is a READ-ONLY reporting layer that serves
    only a static HTML page (`python -m app.dashboard`). It exposes no browser
    JSON API. Phase 15 adds a React presentation frontend. Per the project rule
    ("do not invent a browser API; prefer the existing report/data contract"),
    the React app consumes the SAME typed `DashboardData` view model that the
    existing HTML dashboard already renders.

HOW:
    This module serializes `DashboardService().build()` — the exact real data
    assembled from the Phase 10 final report, the RAG knowledge catalog and the
    Phase 11 refinement result — into `reports/dashboard_data.json`, mirroring
    the existing `reports/final_report.json` / `reports/dashboard.html` artifacts.

    Serialization is driven by the `DashboardData` Pydantic model, so the JSON
    shape IS the contract. It can be loaded back with
    `DashboardData.model_validate_json(...)`.

    Nothing here writes project state, mutates config, or triggers the pipeline.
    It is purely additive (a new module + a new artifact); dashboard server and
    all existing behavior are unchanged.

HOW TO RUN:
    python -m app.dashboard.dump [--out reports/dashboard_data.json]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.dashboard import models as vm
from app.dashboard.provider import PROJECT_ROOT
from app.dashboard.service import DashboardService


def build_data_json(indent: int = 2) -> tuple[vm.DashboardData, str]:
    """Return (data, pretty JSON string) from the real dashboard services."""
    data = DashboardService().build()
    body = data.model_dump_json(indent=indent)
    return data, body


def dump_to(
    out_path: str | Path,
    indent: int = 2,
    print_summary: bool = True,
) -> Path:
    """Serialize the real DashboardData to a JSON file (read-only source)."""
    data, body = build_data_json(indent=indent)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if print_summary:
        ov = data.overview
        print("DashboardData exported (Phase 15, read-only dump):")
        print(f"  project   : {ov.project_name}")
        print(f"  phases    : {ov.completed_phases}/{ov.total_phases} completed "
              f"(current {ov.current_phase})")
        print(f"  tests     : final result total={data.final_status.final_test_result.get('total')} "
              f"passed={data.final_status.final_test_result.get('passed')} "
              f"failed={data.final_status.final_test_result.get('failed')}")
        print(f"  sections  : A-I from DashboardService.build()")
        print(f"  wrote     : {path}")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Export the real DashboardData JSON for the React frontend.")
    parser.add_argument(
        "--out", default=str(PROJECT_ROOT / "reports" / "dashboard_data.json"),
        help="Output JSON path (default: reports/dashboard_data.json)")
    args = parser.parse_args(argv)
    dump_to(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_data_json", "dump_to", "main"]
