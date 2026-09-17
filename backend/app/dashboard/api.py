"""
Phase 15 — read-only JSON API server for the React frontend.

WHY:
    The Phase 15 React frontend must talk to the REAL Python backend over HTTP.
    The dashboard server already builds the complete typed `DashboardData` view
    model (sections A-I) from real project data. This module exposes that SAME
    model as a small, read-only JSON API, keeps the legacy HTML dashboard at
    `/dashboard.html`, and handles CORS for the Vite dev/build origins.

    No browser API is invented and no backend business logic is added:
    `/api/dashboard` returns exactly the data `DashboardService().build()`
    already produces (and that `python -m app.dashboard.dump` writes to
    `reports/dashboard_data.json`). `/api/health` never exposes secrets — only
    the generation mode / project identifiers / final test totals.

ENDPOINTS:
    GET /api/dashboard    -> full DashboardData (sections A-I) as JSON
    GET /api/health       -> {status, service, generation_mode, ...} (no secrets)
    GET /dashboard.html   -> legacy read-only HTML dashboard
    GET /                 -> endpoint listing

CORS:
    Requests from configured browser origins (defaults to the common local dev
    origins, override via `DASHBOARD_CORS_ORIGINS` in `backend/.env`) receive
    CORS headers, including OPTIONS preflight. The allow-origin is echoed only
    for an explicitly allowed requesting origin (never `*`).

RUN:
    python -m app.dashboard --port 8877
"""

from __future__ import annotations

import json
import socketserver
from http.server import BaseHTTPRequestHandler

from app.dashboard import models as vm
from app.dashboard import provider, render
from app.dashboard.service import DashboardService

DEFAULT_CORS_ORIGIN = "http://localhost:5173"
DEFAULT_CORS_ORIGINS = frozenset({
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
})
LEGACY_HTML_PATH = "/dashboard.html"
API_VERSION = 1

_ENDPOINT_INDEX = {
    "/api/health": "backend status (no secrets)",
    "/api/dashboard": "full DashboardData (sections A-I) as JSON",
    LEGACY_HTML_PATH: "legacy read-only HTML dashboard",
}


class ApiContext:
    """Everything the server serves, built ONCE at startup (read-only)."""

    def __init__(self, data: vm.DashboardData, generation_mode: str) -> None:
        self.data = data
        self.generation_mode = generation_mode
        self.html = render.render_html(data).encode("utf-8")
        self.dashboard_json = data.model_dump_json(indent=2)


def make_context(cfg=None) -> ApiContext:
    """Build the REAL DashboardData (report + RAG catalog + refinement)."""
    cfg = cfg or provider.default_settings()
    redacted = provider.RedactedConfig(cfg)
    mode = "MOCK" if redacted.mock_mode else "REAL LLM"
    data = DashboardService(cfg=cfg).build()
    return ApiContext(data=data, generation_mode=mode)


def _parse_origins(raw: str | None) -> frozenset[str]:
    """Split a comma-separated CORS origin list into a set."""
    if not raw:
        return DEFAULT_CORS_ORIGINS
    origins = {o.strip() for o in raw.split(",") if o.strip()}
    return origins or DEFAULT_CORS_ORIGINS


def health_payload(ctx: ApiContext) -> dict:
    ov = ctx.data.overview
    result = ctx.data.final_status.final_test_result or {}
    return {
        "status": "ok",
        "service": "autonomous-rag-iot-dashboard",
        "api_version": API_VERSION,
        "generation_mode": ctx.generation_mode,
        "project_name": ov.project_name,
        "project_id": ov.project_id,
        "analysis_id": ov.analysis_id,
        "current_phase": ov.current_phase,
        "completed_phases": ov.completed_phases,
        "total_phases": ov.total_phases,
        "final_test_result": {
            "total": result.get("total"),
            "passed": result.get("passed"),
            "failed": result.get("failed"),
            "errors": result.get("errors"),
            "skipped": result.get("skipped"),
        },
        "endpoints": dict(_ENDPOINT_INDEX),
    }


class DashboardApiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AutonomousRAGIoTHttp/1.0"
    sys_version = ""

    # The server instance carries the immutable context + allowed origins.
    server: "DashboardApiServer"  # type: ignore[misc]

    def log_message(self, *args):  # noqa: N802  (quiet; app logs via loguru)
        return

    # ------------------------------------------------------------- CORS

    def _cors_origin(self) -> str | None:
        requested = self.headers.get("Origin")
        if requested and requested in self.server.allowed_origins:
            return requested
        return None

    def _cors_headers(self) -> dict[str, str]:
        origin = self._cors_origin()
        if origin is None:
            return {}
        return {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept",
            "Access-Control-Max-Age": "86400",
        }

    # ----------------------------------------------------------- helpers

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._respond(status, body, "application/json; charset=utf-8")

    # ----------------------------------------------------------- methods

    def do_OPTIONS(self):  # noqa: N802  (CORS preflight)
        self._respond(204, b"", "text/plain; charset=utf-8")

    def do_GET(self):  # noqa: N802
        path = (self.path.split("?", 1)[0].rstrip("/")) or "/"
        if path == "/api/dashboard":
            self._respond(200, self.server.api_context.dashboard_json.encode("utf-8"),
                          "application/json; charset=utf-8")
        elif path == "/api/health":
            self._send_json(200, health_payload(self.server.api_context))
        elif path == LEGACY_HTML_PATH:
            self._respond(200, self.server.api_context.html,
                          "text/html; charset=utf-8")
        elif path == "/":
            self._send_json(200, {
                "service": "Autonomous RAG-Based IoT Test Generation & "
                           "Fault Detection Framework",
                "api_version": API_VERSION,
                "generation_mode": self.server.api_context.generation_mode,
                "endpoints": dict(_ENDPOINT_INDEX),
            })
        else:
            self._send_json(404, {"error": "Not found", "path": path})


class DashboardApiServer(socketserver.ThreadingTCPServer):
    """Threaded HTTP server that carries the read-only API context / CORS."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, handler_cls,
                 api_context: ApiContext,
                 allowed_origins: frozenset[str]) -> None:
        self.api_context = api_context
        self.allowed_origins = allowed_origins
        super().__init__(server_address, handler_cls)


def run_server(host: str = "127.0.0.1", port: int = 8000,
               cfg=None, cors_origins: str | None = None) -> None:
    ctx = make_context(cfg)
    origins = _parse_origins(cors_origins)
    with DashboardApiServer((host, port), DashboardApiHandler, ctx, origins) as httpd:
        print("=" * 60)
        print(" Project Dashboard + JSON API (read-only)")
        print(f" Generation mode : {ctx.generation_mode}")
        print(f" API             : http://{host}:{port}/api/dashboard")
        print(f" Health          : http://{host}:{port}/api/health")
        print(f" Legacy HTML     : http://{host}:{port}/dashboard.html")
        print(f" CORS origins    : {', '.join(sorted(origins))}")
        print(" Press Ctrl+C to stop.")
        print("=" * 60)
        httpd.serve_forever()


__all__ = [
    "API_VERSION",
    "ApiContext",
    "DashboardApiHandler",
    "DashboardApiServer",
    "DEFAULT_CORS_ORIGIN",
    "DEFAULT_CORS_ORIGINS",
    "LEGACY_HTML_PATH",
    "health_payload",
    "make_context",
    "run_server",
]