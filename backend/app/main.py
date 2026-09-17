"""
WHAT:
    The application entry point. In later phases this will orchestrate
    the full pipeline (spec -> requirements -> RAG -> LLM -> validation
    -> execution -> faults -> analysis -> refinement -> dashboard/report).

WHY (for Phase 1):
    Right now there is no pipeline to run yet — Phase 1's job is only to
    prove the project skeleton is wired correctly: settings load from
    .env, logging works, and the directory structure is in place. This
    is the smallest possible thing we can run and verify before adding
    any real logic in Phase 2 onward.

HOW TO RUN:
    From the project root, with the virtual environment active:
        python run.py

EXPECTED OUTPUT:
    A startup banner printed to the console showing the loaded
    environment, LLM mode (mock/real), and MQTT broker target, plus a
    log line confirming logging is working.
"""

from __future__ import annotations

from loguru import logger

from app.config import settings
from app.logging_config import setup_logging


def run() -> None:
    setup_logging()

    logger.info("Starting Autonomous RAG-Based IoT Test Generation Framework")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(
        f"LLM mode: {'MOCK (no API key configured)' if settings.is_mock_llm else settings.llm_provider}"
    )
    logger.info(
        f"MQTT broker target: {settings.mqtt_broker_host}:{settings.mqtt_broker_port}"
    )
    logger.info(f"Database URL: {settings.database_url}")
    logger.info(
        f"Refinement targets: coverage>={settings.target_requirement_coverage}%, "
        f"fault_detection>={settings.target_fault_detection}%, "
        f"max_iterations={settings.max_refinement_iterations}"
    )
    logger.info(
        "Phase 1 skeleton is working. No pipeline logic exists yet — "
        "that starts in Phase 2 (IoT simulator)."
    )


if __name__ == "__main__":
    run()
