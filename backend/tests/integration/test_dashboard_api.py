"""
Phase 15 — dashboard JSON API integration tests.

Starts the real dashboard server (ThreadingTCPServer) on an ephemeral port with
a REAL `DashboardData` build and verifies the HTTP contract the React frontend
consumes: /api/dashboard, /api/health, CORS allow/deny + preflight, 404 JSON,
and the legacy /dashboard.html page. Everything is read-only.
"""

from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from app.dashboard import api
from app.dashboard import models as vm

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
}
DISALLOWED_ORIGIN = "http://evil.example"


@pytest.fixture(scope="module")
def server():
    ctx = api.make_context()  # one real build for the whole module
    httpd = api.DashboardApiServer(
        ("127.0.0.1", 0), api.DashboardApiHandler, ctx,
        frozenset(ALLOWED_ORIGINS),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}"
    yield base, ctx
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def _request(base, path, origin=None, method="GET"):
    req = Request(base + path, method=method)
    if origin:
        req.add_header("Origin", origin)
    if method == "OPTIONS":
        req.add_header("Access-Control-Request-Method", "GET")
    try:
        res = urlopen(req, timeout=60)
        return res.status, dict(res.headers.items()), res.read()
    except HTTPError as err:  # 404 / 500 responses come back as HTTPError
        return err.code, dict(err.headers.items()), err.read()


def test_api_dashboard_endpoint_serves_the_real_contract(server):
    base, ctx = server
    status, headers, body = _request(base, "/api/dashboard")
    assert status == 200
    assert headers.get("Content-Type", "").startswith("application/json")
    payload = json.loads(body)
    # The served JSON is the exact real contract the frontend consumes.
    assert set(payload) == {
        "overview", "requirements", "knowledge", "generation",
        "execution", "fault_summary", "refinement", "traceability",
        "final_status",
    }
    data = vm.DashboardData.model_validate(payload)
    assert data.overview.project_id == ctx.data.overview.project_id
    assert data.overview.generation_mode == ctx.data.overview.generation_mode
    assert data.final_status.final_test_result == ctx.data.final_status.final_test_result
    assert [r.requirement_id for r in data.requirements] == \
        [r.requirement_id for r in ctx.data.requirements]
    assert data.knowledge.document_count == ctx.data.knowledge.document_count
    assert data.refinement.available is True


def test_api_dashboard_values_are_real(server):
    base, ctx = server
    _, _, body = _request(base, "/api/dashboard")
    payload = json.loads(body)
    # Real project data (the report on disk records the real pytest total).
    result = payload["final_status"]["final_test_result"]
    assert result["passed"] > 0
    assert result["failed"] == 0
    assert payload["overview"]["project_name"]
    assert payload["generation"]["generation_mode"] in {"MOCK", "REAL LLM"}


def test_api_health_endpoint_has_no_secrets(server):
    base, _ = server
    status, _, body = _request(base, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["status"] == "ok"
    assert payload["generation_mode"] in {"MOCK", "REAL LLM"}
    assert payload["project_name"]
    assert payload["final_test_result"]["passed"] > 0
    # Never expose secrets/keys in the API.
    assert "llm_api_key" not in payload
    assert "sk-" not in body.decode("utf-8", errors="ignore")


@pytest.mark.parametrize("origin", sorted(ALLOWED_ORIGINS))
def test_api_cors_allows_each_frontend_origin(server, origin):
    base, _ = server
    status, headers, _ = _request(base, "/api/health", origin=origin)
    assert status == 200
    assert headers.get("Access-Control-Allow-Origin") == origin


def test_api_cors_rejects_other_origins(server):
    base, _ = server
    status, headers, _ = _request(base, "/api/health", origin=DISALLOWED_ORIGIN)
    assert status == 200  # resource still serves (CORS is browser-enforced)
    assert "Access-Control-Allow-Origin" not in headers


@pytest.mark.parametrize("origin", sorted(ALLOWED_ORIGINS))
def test_api_cors_preflight_for_allowed_origin(server, origin):
    base, _ = server
    status, headers, _ = _request(
        base, "/api/dashboard", origin=origin, method="OPTIONS")
    assert status in {200, 204}
    assert headers.get("Access-Control-Allow-Origin") == origin
    assert "GET" in headers.get("Access-Control-Allow-Methods", "")


def test_api_unknown_path_returns_json_404(server):
    base, _ = server
    status, headers, body = _request(base, "/api/does-not-exist")
    assert status == 404
    assert headers.get("Content-Type", "").startswith("application/json")
    assert "error" in json.loads(body)


def test_legacy_html_dashboard_still_served(server):
    base, _ = server
    status, headers, body = _request(base, "/dashboard.html")
    assert status == 200
    assert headers.get("Content-Type", "").startswith("text/html")
    assert b"Project Overview" in body


def test_root_endpoint_lists_apis(server):
    base, _ = server
    status, _, body = _request(base, "/")
    assert status == 200
    payload = json.loads(body)
    assert "/api/dashboard" in payload["endpoints"]
    assert "/api/health" in payload["endpoints"]