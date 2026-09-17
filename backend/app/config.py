"""
Central configuration for the whole framework.

WHAT:
    A single `Settings` object (Pydantic BaseSettings) that reads values
    from environment variables / a `.env` file, validates their types,
    and exposes them as normal Python attributes.

WHY:
    Every module (RAG, LLM, MQTT, database, dashboard...) needs config
    values like API keys, broker host, or target coverage thresholds.
    Instead of each module reading `os.environ` directly (error-prone,
    no validation, easy to typo a variable name), they all import this
    one `settings` object. If a required variable is missing or has the
    wrong type, the app fails fast at startup with a clear error instead
    of failing deep inside some module hours later.

HOW:
    Pydantic's BaseSettings automatically:
      1. Reads the `.env` file (via python-dotenv under the hood).
      2. Falls back to real OS environment variables if `.env` is absent.
      3. Validates each field's type (e.g. MQTT_BROKER_PORT must be int).
      4. Provides sensible defaults where it's safe to do so.

HOW TO RUN:
    Not run directly — imported by other modules, e.g.:
        from app.config import settings
        print(settings.mqtt_broker_host)

HOW TO VERIFY:
    Run `python -c "from app.config import settings; print(settings)"`
    from the project root. It should print all loaded settings without
    raising a validation error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to the project root (the folder that contains this app/ dir).
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All configuration values for the framework, loaded from .env."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_env: Literal["development", "testing", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- LLM provider ---
    # "mock" mode requires no API key and returns clearly-labeled fake
    # data so the pipeline is runnable/demoable before Phase 6/7 wiring
    # of a real LLM, or whenever no API key is configured.
    llm_provider: Literal["mock", "openai", "anthropic"] = Field(
        default="mock", alias="LLM_PROVIDER"
    )
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")

    # --- Embeddings ---
    embedding_provider: Literal["local", "openai"] = Field(
        default="local", alias="EMBEDDING_PROVIDER"
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL"
    )
    # Dimension of the deterministic local (hashing) embedding vectors.
    embedding_dimension: int = Field(default=256, alias="EMBEDDING_DIMENSION")
    # Separate key for embedding providers that need one (OpenAI).
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")

    # --- RAG knowledge base ---
    rag_knowledge_dir: str = Field(
        default="knowledge_base/documents", alias="RAG_KNOWLEDGE_DIR"
    )
    rag_chroma_dir: str = Field(
        default="knowledge_base/chroma", alias="RAG_CHROMA_DIR"
    )
    rag_collection_name: str = Field(
        default="iot_knowledge", alias="RAG_COLLECTION_NAME"
    )
    rag_chunk_size: int = Field(default=600, alias="RAG_CHUNK_SIZE")
    rag_chunk_overlap: int = Field(default=80, alias="RAG_CHUNK_OVERLAP")
    rag_top_k: int = Field(default=4, alias="RAG_TOP_K")

    # --- MQTT ---
    mqtt_broker_host: str = Field(default="localhost", alias="MQTT_BROKER_HOST")
    mqtt_broker_port: int = Field(default=1883, alias="MQTT_BROKER_PORT")
    mqtt_client_id: str = Field(
        default="iot_test_framework", alias="MQTT_CLIENT_ID"
    )
    mqtt_keepalive_seconds: int = Field(default=60, alias="MQTT_KEEPALIVE_SECONDS")
    mqtt_connect_timeout_seconds: float = Field(
        default=5.0, alias="MQTT_CONNECT_TIMEOUT_SECONDS"
    )
    mqtt_reconnect_delay_seconds: float = Field(
        default=1.0, alias="MQTT_RECONNECT_DELAY_SECONDS"
    )
    mqtt_max_reconnect_attempts: int = Field(
        default=5, alias="MQTT_MAX_RECONNECT_ATTEMPTS"
    )
    mqtt_qos: int = Field(default=1, alias="MQTT_QOS", ge=0, le=2)

    # --- MQTT topics ---
    mqtt_topic_temperature: str = Field(
        default="iot/sensor/temperature", alias="MQTT_TOPIC_TEMPERATURE"
    )
    mqtt_topic_status: str = Field(
        default="iot/sensor/status", alias="MQTT_TOPIC_STATUS"
    )
    mqtt_topic_fault: str = Field(
        default="iot/test/fault", alias="MQTT_TOPIC_FAULT"
    )

    # --- Execution engine (Phase 8) ---
    # Per-test wall-clock budget; exceeding it turns the test into an ERROR.
    execution_max_duration_seconds: float = Field(
        default=10.0, alias="EXECUTION_MAX_DURATION_SECONDS", gt=0
    )
    # Hard cap on individual WAIT actions; larger requests are rejected.
    execution_max_wait_seconds: float = Field(
        default=5.0, alias="EXECUTION_MAX_WAIT_SECONDS", gt=0
    )

    # --- Database ---
    database_url: str = Field(
        default="sqlite:///./data/framework.db", alias="DATABASE_URL"
    )
    # Directory where generated reports are written (relative to project root).
    report_dir: str = Field(default="reports", alias="REPORT_DIR")

    # --- Refinement loop ---
    max_refinement_iterations: int = Field(
        default=3, alias="MAX_REFINEMENT_ITERATIONS"
    )
    target_requirement_coverage: float = Field(
        default=90.0, alias="TARGET_REQUIREMENT_COVERAGE"
    )
    target_fault_detection: float = Field(
        default=90.0, alias="TARGET_FAULT_DETECTION"
    )

    # --- Dashboard API / CORS ---
    # Comma-separated browser origins allowed to call the read-only JSON API
    # served by `python -m app.dashboard` (the Phase 15 React frontend).
    dashboard_cors_origins: str = Field(
        default=(
            "http://localhost:5173,http://localhost:5174,"
            "http://127.0.0.1:5173,http://127.0.0.1:5174"
        ),
        alias="DASHBOARD_CORS_ORIGINS"
    )

    @property
    def is_mock_llm(self) -> bool:
        """True when no real LLM should be called (safe default)."""
        return self.llm_provider == "mock" or not self.llm_api_key


# A single shared instance every other module should import.
settings = Settings()
