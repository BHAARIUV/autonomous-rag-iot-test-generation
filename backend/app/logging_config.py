"""
WHAT:
    Configures a single shared logger (via loguru) used across the whole
    framework, writing to both the console and a rotating log file.

WHY:
    Rule #8 requires logging throughout the project. Rather than each
    module configuring its own logger differently, we set this up once
    at startup and every module just does `from loguru import logger`.

HOW:
    loguru's default logger is reconfigured: console output at the level
    from Settings.log_level, plus a file sink under logs/ that rotates
    once it hits 5 MB so log files don't grow unbounded during a long
    refinement run.

HOW TO VERIFY:
    Run `python -c "from app.logging_config import setup_logging; setup_logging(); \
    from loguru import logger; logger.info('test message')"` — you should
    see a formatted line in the console AND a new file under logs/.
"""

from __future__ import annotations

import sys

from loguru import logger

from app.config import PROJECT_ROOT, settings

_configured = False


def setup_logging() -> None:
    """Configure loguru sinks. Safe to call multiple times (no-op after first)."""
    global _configured
    if _configured:
        return

    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    logger.remove()  # remove loguru's default handler so we control format
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        ),
    )
    logger.add(
        logs_dir / "framework.log",
        level="DEBUG",
        rotation="5 MB",
        retention=5,
        encoding="utf-8",
    )

    _configured = True
