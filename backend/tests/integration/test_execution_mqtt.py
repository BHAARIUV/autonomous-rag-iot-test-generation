"""
Phase 8 integration tests — MQTT-backed execution against a real broker
(local Mosquitto; see README "Mosquitto setup").

These tests are agent-marked: skipped (never faked) if no broker is
reachable. When the broker is up, generated MQTT communication test cases
are executed end-to-end and the executor's own PUBACK / message-count
assertions are checked against real broker delivery.

Contract under test:
- a generated COMMUNICATION case (subscribe -> trigger publication ->
  validate payload) executes to PASS with at least one real received message,
- the QoS-1 (AT_LEAST_ONCE) case executes to PASS against the broker,
- every executed action is still from the closed whitelisted action set
  even when MQTT is involved.
"""

import socket
import time
import uuid

import pytest

from app.config import settings, Settings
from app.ingestion.service import ingest_text
from app.llm.service import GenerationService
from app.rag.service import RagService
from app.testing import ExecutionService
from app.testing.actions import TestActionType
from app.testing.models import TestStatus


def _broker_is_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


BROKER_AVAILABLE = _broker_is_reachable(settings.mqtt_broker_host, settings.mqtt_broker_port)

pytestmark = pytest.mark.skipif(
    not BROKER_AVAILABLE,
    reason=(
        f"No MQTT broker reachable at {settings.mqtt_broker_host}:"
        f"{settings.mqtt_broker_port} — start Mosquitto to run these tests "
        f"(see README 'Mosquitto setup')."
    ),
)


@pytest.fixture
def mqtt_pipeline(tmp_path):
    cfg = Settings(
        _env_file=None,
        RAG_CHROMA_DIR=str(tmp_path / "chroma"),
        RAG_COLLECTION_NAME="int_execution_mqtt",
        RAG_CHUNK_SIZE=600,
        RAG_CHUNK_OVERLAP=80,
        RAG_TOP_K=4,
        EMBEDDING_PROVIDER="local",
        EMBEDDING_DIMENSION=256,
        LLM_PROVIDER="mock",
        LLM_MODEL="mock-llm",
    )
    rag = RagService(settings_=cfg)
    assert rag.index_knowledge_base().document_count == 12
    generator = GenerationService(settings_=cfg, rag_service=rag)
    executor = ExecutionService(settings_=cfg)
    yield generator, executor
    rag.close()


def _mqtt_suite(generator):
    spec = ingest_text(
        "Device: Temperature Sensor\n"
        "Range: -40 C to 125 C\n"
        "Accuracy: 0.5 C\n"
        "Sampling Interval: 1 s\n"
        "Communication Protocol: MQTT\n",
        source="temperature_sensor.txt",
    )
    requirement = {r.requirement_id: r for r in spec.requirements}["REQ-004"]
    return generator.generate_for_requirement(requirement, top_k=4)


def test_generated_communication_case_executes_against_broker(mqtt_pipeline, tmp_path):
    generator, executor = mqtt_pipeline
    suite = _mqtt_suite(generator)
    communication = [tc for tc in suite.test_cases if tc.category.value == "COMMUNICATION"]
    result = executor.execute_test_case(communication[0])

    assert result.status is TestStatus.PASS
    assert result.mqtt_information is not None
    assert result.mqtt_information.broker == f"{settings.mqtt_broker_host}:{settings.mqtt_broker_port}"
    assert result.mqtt_information.received_count >= 1
    assert result.mqtt_information.invalid_count == 0

    allowed = {a.value for a in TestActionType}
    assert all(e.action in allowed for e in result.execution_evidence)


def test_generated_qos1_at_least_once_case_executes_against_broker(mqtt_pipeline):
    generator, executor = mqtt_pipeline
    suite = _mqtt_suite(generator)
    at_least_once = [tc for tc in suite.test_cases if "AT_LEAST_ONCE" in str(tc.test_data.expected)]
    assert len(at_least_once) == 1

    result = executor.execute_test_case(at_least_once[0])
    assert result.status is TestStatus.PASS
    assert result.mqtt_information.received_count >= 1
    # QoS-1 delivery produces the ack-assertion step too
    ack_steps = [e for e in result.execution_evidence if e.action == "ASSERT_MESSAGE"]
    assert len(ack_steps) >= 1


def test_every_generated_mqtt_case_can_connect_without_crash(mqtt_pipeline):
    """Honest boundary: even non-MQTT cases in a COMMUNICATION suite run cleanly."""
    generator, executor = mqtt_pipeline
    suite = _mqtt_suite(generator)

    for tc in suite.test_cases:
        result = executor.execute_test_case(tc)
        assert result.status in {TestStatus.PASS, TestStatus.FAIL, TestStatus.ERROR}
        if result.status is TestStatus.ERROR:
            assert result.error_message, "ERROR result must explain itself"
        assert result.execution_evidence  # every case produced an audit trail