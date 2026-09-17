"""
Phase 12/15 — dashboard server entry point.

Serves the read-only dashboard over HTTP. The full real `DashboardData` is
built once on startup (report + RAG catalog + refinement), then served
read-only from memory:

    GET /api/dashboard    -> full DashboardData (sections A-I) as JSON
    GET /api/health       -> backend status (no secrets)
    GET /dashboard.html   -> legacy read-only HTML dashboard
    GET /                 -> endpoint listing

CORS is handled for the configured browser origins (default the common local
dev origins http://localhost:5173/5174 and http://127.0.0.1:5173/5174; override
via DASHBOARD_CORS_ORIGINS in backend/.env), so the Phase 15 React/Vite
frontend can call the API directly.

HOW TO RUN:
    python -m app.dashboard              # http://127.0.0.1:8000
    python -m app.dashboard --port 8877  # the port the React frontend uses by default
"""

from __future__ import annotations

import argparse

from app.config import settings
from app.dashboard import api


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Serve the read-only project dashboard + JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--cors-origins", default=None,
        help="Comma-separated browser origins allowed to call the JSON API "
             "(default: DASHBOARD_CORS_ORIGINS or the common local dev origins).")
    args = parser.parse_args(argv)
    cors_origins = args.cors_origins or settings.dashboard_cors_origins
    api.run_server(host=args.host, port=args.port, cors_origins=cors_origins)


if __name__ == "__main__":
    main()