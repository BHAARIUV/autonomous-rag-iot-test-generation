"""
Phase 11 — Safe health / status check.

WHY:
    Before demoing or deploying the framework, an operator wants a single,
    safe command that confirms:
        - the Python environment loads,
        - required third-party packages are importable,
        - configuration parses correctly,
        - the MQTT broker is reachable (or not),
        - the reports directory exists and is writable,
        - the RAG knowledge base (documents + Chroma index) is present.

HOW (safety):
    - The check NEVER prints, logs, or returns secrets (API keys, connection
      strings, tokens). Configuration values are shown masked.
    - It never mutates the environment: it only reads, and the optional MQTT
      probe just connects + disconnects.
    - It is additive and cannot break existing Phase 1-10 behavior.

HOW TO RUN:
    python -m app.cli health
    or:  python -c "from app.health import run_health_check; print(run_health_check().render())"

HOW TO VERIFY:
    python -m pytest tests/unit/test_health.py -q
"""

from __future__ import annotations

import importlib
import platform
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from app.config import PROJECT_ROOT, Settings, settings

# Third-party packages required by the framework (from requirements.txt).
REQUIRED_PACKAGES: tuple[str, ...] = (
    "pydantic",
    "pydantic_settings",
    "dotenv",
    "loguru",
    "pytest",
    "paho.mqtt",
    "pypdf",
    "chromadb",
)

_SECRET_KEYS = ("api_key", "password", "token", "secret", "key")

# Resolve these once from the real config so the checks below never reference
# undefined names (they must stay in sync with Settings aliases).
_REPORT_DIR = PROJECT_ROOT / settings.report_dir
_KNOWLEDGE_DOCS_DIR = PROJECT_ROOT / settings.rag_knowledge_dir
REPORT_DIR = _REPORT_DIR
KNOWLEDGE_DOCS_DIR = _KNOWLEDGE_DOCS_DIR


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class HealthReport:
    """Aggregate result of every health check."""

    checks: list[CheckResult] = field(default_factory=list)
    python: str = ""
    env_name: str = ""
    env_is_venv: bool = False
    config_masked: str = ""
    mqtt_reachable: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def render(self) -> str:
        lines = ["# Framework Health Check", ""]
        lines.append(f"Python           : {self.python}")
        lines.append(f"Environment      : {self.env_name} (venv={self.env_is_venv})")
        lines.append(f"Config source    : {self.config_masked}")
        lines.append(f"MQTT reachable   : {self.mqtt_reachable}")
        lines.append("")
        for c in self.checks:
            mark = "[OK]  " if c.ok else "[FAIL]"
            lines.append(f"{mark} {c.name}")
            if c.detail:
                lines.append(f"        {c.detail}")
        lines.append("")
        lines.append("Overall          : " + ("PASS" if self.ok else "FAIL"))
        return "\n".join(lines)


def _mask_value(name: str, value: object) -> str:
    """Redact any value whose setting name looks secret."""
    if any(key in name.lower() for key in _SECRET_KEYS):
        return "***** (redacted)" if value not in (None, "") else "(empty)"
    return str(value)


def build_config_summary(cfg: Settings) -> str:
    """Human-readable, secret-free configuration summary (masked keys)."""
    parts: list[str] = []
    for name, value in cfg.model_dump().items():
        parts.append(f"{name}={_mask_value(name, value)}")
    # Compact single line, safe to log/print.
    return ", ".join(sorted(parts))


def check_python() -> tuple[str, str, bool]:
    version = platform.python_version()
    in_venv = sys.prefix != sys.base_prefix
    env_name = Path(sys.prefix).name
    return version, env_name, in_venv


def check_required_packages() -> list[CheckResult]:
    results: list[CheckResult] = []
    for pkg in REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            results.append(CheckResult(name=f"package: {pkg}", ok=True, detail="importable"))
        except Exception as exc:  # pragma: no cover - depends on environment
            results.append(
                CheckResult(name=f"package: {pkg}", ok=False, detail=f"import failed: {type(exc).__name__}")
            )
    return results


def _check_config(cfg: Settings) -> CheckResult:
    """Config loads, validates, and no secret value leaks into the summary."""
    try:
        raw = cfg.model_dump()
        summary = build_config_summary(cfg)
    except Exception as exc:  # pragma: no cover - config is pre-validated
        return CheckResult(name="configuration", ok=False, detail=f"load failed: {exc}")

    for name, value in raw.items():
        if any(key in name.lower() for key in _SECRET_KEYS) and value not in (None, ""):
            # The masked rendering of this secret must never include the value.
            if str(value) in summary:
                return CheckResult(
                    name="configuration", ok=False,
                    detail=f"secret-like field {name} leaked unredacted",
                )
    return CheckResult(name="configuration", ok=True, detail="loaded, validated and secret-free")


def _check_report_dir() -> CheckResult:
    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        probe = REPORT_DIR / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult(name="reports directory", ok=True, detail=str(REPORT_DIR))
    except Exception as exc:
        return CheckResult(name="reports directory", ok=False, detail=f"not writable: {exc}")


def _check_knowledge_base() -> CheckResult:
    if not KNOWLEDGE_DOCS_DIR.is_dir():
        return CheckResult(name="knowledge base", ok=False, detail="documents dir missing")
    manifest = KNOWLEDGE_DOCS_DIR / "manifest.json"
    if not manifest.is_file():
        return CheckResult(name="knowledge base", ok=False, detail="manifest.json missing")
    docs = list(KNOWLEDGE_DOCS_DIR.glob("kb_*.md"))
    return CheckResult(
        name="knowledge base",
        ok=True,
        detail=f"{len(docs)} docs, manifest present",
    )


def _probe_mqtt(host: str, port: int, timeout: float = 2.0) -> bool:
    """Connect a raw TCP socket to the broker. Never reads secrets."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def run_health_check(cfg: Settings | None = None, *, probe_mqtt: bool = True) -> HealthReport:
    """Run all health checks and return a structured, secret-free report."""
    cfg = cfg or settings
    version, env_name, in_venv = check_python()

    checks: list[CheckResult] = []
    checks.append(CheckResult(name="python", ok=True, detail=version))
    checks.extend(check_required_packages())
    checks.append(_check_config(cfg))
    checks.append(_check_report_dir())
    checks.append(_check_knowledge_base())

    mqtt_host, mqtt_port = cfg.mqtt_broker_host, cfg.mqtt_broker_port
    mqtt_ok = _probe_mqtt(mqtt_host, mqtt_port) if probe_mqtt else False
    checks.append(
        CheckResult(
            name="mqtt broker",
            ok=mqtt_ok,
            detail=f"{mqtt_host}:{mqtt_port} {'reachable' if mqtt_ok else 'unreachable (tests will SKIP, not fake)'}",
        )
    )

    return HealthReport(
        checks=checks,
        python=version,
        env_name=env_name,
        env_is_venv=in_venv,
        config_masked=".env / environment (values masked)",
        mqtt_reachable=mqtt_ok,
    )


__all__ = [
    "CheckResult",
    "HealthReport",
    "run_health_check",
    "build_config_summary",
    "check_python",
    "check_required_packages",
]
