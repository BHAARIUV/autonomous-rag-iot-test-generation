"""
Phase 8 — structured execution-result models.

WHY:
    Every executed test must be auditable: a reviewer has to be able to see
    WHY a test passed or failed, what each action observed, what it expected,
    which fault was active, and exactly which requirement/test case an
    execution belongs to. One strict, frozen, JSON-serializable schema forces
    every downstream consumer (reporting, coverage, analysis) to speak the
    same language and keeps FAIL clearly distinct from ERROR:

        PASS     — all steps OK and every assertion passed
        FAIL     — an assertion WAS evaluated and the expected behavior was
                   NOT observed (device is fine, expectation is wrong)
        ERROR    — execution could not be completed correctly (unknown
                   action, invalid params, timeout, unavailable device...)
        SKIPPED  — execution was deliberately not attempted because of a
                   known execution condition (e.g. no MQTT broker)

HOW (traceability):
    execution_id (unique run) -> test_case_id -> requirement_id survives on
    the result AND on every StepEvidence record, so the chain
    requirement -> test case -> execution -> evidence is never broken.

HOW TO VERIFY:
    See tests/unit/test_execution_models.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.iot.models import SensorStatus


class TestStatus(str, Enum):
    """Final status of an executed test (FAIL and ERROR are NOT ambiguous)."""

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class StepOutcome(str, Enum):
    """Outcome of one executed step (actions, not assertions)."""

    OK = "OK"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Per-step evidence
# ---------------------------------------------------------------------------


class StepEvidence(BaseModel):
    """One step of an execution: what was done, what was observed, what was
    expected, and what happened. This is the audit trail of a single action."""

    model_config = {"frozen": True}

    step_number: int = Field(ge=1)
    action: str = Field(description="Structured action label, e.g. 'SET_TEMPERATURE'")
    source_step_text: str = Field(
        default="", description="Original test-step prose this action came from"
    )
    action_result: StepOutcome
    assertion_result: TestStatus | None = Field(
        default=None, description="Set only if this step ran an assertion"
    )
    expected: str | None = Field(default=None, description="What the step expected")
    observed: str | None = Field(default=None, description="What the device/system actually reported")
    failure_reason: str | None = Field(
        default=None, description="Human-readable WHY (assertion mismatch / skip reason)"
    )
    error_message: str | None = Field(default=None, description="Typed error detail, if any")
    timestamp: datetime = Field(default_factory=_now_utc)
    duration: float = Field(default=0.0, ge=0.0)

    @property
    def passed(self) -> bool:
        """A step passes when its action succeeded AND any assertion passed."""
        if self.action_result is not StepOutcome.OK:
            return False
        return self.assertion_result in (None, TestStatus.PASS)


# ---------------------------------------------------------------------------
# Environment / device snapshots (context captured at the end of a run)
# ---------------------------------------------------------------------------


class SimulatorStateSnapshot(BaseModel):
    """Snapshot of the simulated device at the end of an execution."""

    model_config = {"frozen": True}

    device_name: str
    status: SensorStatus | None
    tick_count: int = Field(ge=0)
    min_temperature_c: float
    max_temperature_c: float
    accuracy_c: float
    commanded_value: float | None = Field(
        default=None, description="Active SET_TEMPERATURE set-point (if any)"
    )
    last_observed_value: float | None = Field(
        default=None, description="Most recent value reported by a READ"
    )
    seed: int


class SensorMqttView(BaseModel):
    """A light, JSON-safe view of an MQTT-received sensor message."""

    model_config = {"frozen": True}

    sensor_id: str
    temperature: float | None
    status: SensorStatus | None
    valid: bool


class MqttSnapshot(BaseModel):
    """What the MQTT side of this run saw (honest — real counts only)."""

    model_config = {"frozen": True}

    available: bool = Field(description="Was a broker connection available/used")
    connected: bool
    broker: str = Field(default="")
    topic: str | None = Field(default=None, description="Topic subscribed/published last")
    received_count: int = Field(default=0, ge=0)
    invalid_count: int = Field(default=0, ge=0)
    last_received: SensorMqttView | None = Field(default=None)


class EnvironmentSnapshot(BaseModel):
    """Static environment context captured for every execution."""

    model_config = {"frozen": True}

    app_env: str = Field(default="")
    llm_provider: str = Field(default="")
    execution_max_duration_seconds: float = Field(default=0.0, ge=0.0)
    execution_max_wait_seconds: float = Field(default=0.0, ge=0.0)
    mqtt_broker: str = Field(default="", description="host:port targeted by MQTT actions")


# ---------------------------------------------------------------------------
# Full execution result
# ---------------------------------------------------------------------------


class ExecutionResult(BaseModel):
    """The complete, traceable result of executing one test case.

    FAIL vs ERROR contract:
        - status == FAIL    -> an assertion was evaluated and observed did not
          match expected; `failure_reason` explains the mismatch.
        - status == ERROR   -> execution itself could not be completed
          correctly (unknown/invalid action, timeout, unavailable device or
          broker); `error_message` explains the failure.
        - status == SKIPPED -> execution was deliberately not attempted for a
          known condition (e.g. no MQTT broker); `failure_reason` explains.
    """

    model_config = {"frozen": True}

    execution_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex, description="Unique execution id"
    )
    test_case_id: str = Field(description="Traceability: the executed test case")
    requirement_id: str = Field(description="Traceability: the source requirement")
    status: TestStatus
    started_at: datetime = Field(default_factory=_now_utc)
    completed_at: datetime = Field(default_factory=_now_utc)
    duration: float = Field(default=0.0, ge=0.0, description="Wall-clock seconds")
    steps_executed: int = Field(default=0, ge=0)
    steps_passed: int = Field(default=0, ge=0)
    steps_failed: int = Field(default=0, ge=0)
    observed_values: dict[str, str] = Field(
        default_factory=dict, description="Aggregated observed values (label -> value)"
    )
    expected_values: dict[str, str] = Field(
        default_factory=dict, description="Aggregated expected values (label -> value)"
    )
    failure_reason: str | None = Field(
        default=None, description="For FAIL/SKIPPED: why the expectation was not met"
    )
    error_message: str | None = Field(
        default=None, description="For ERROR: the typed error detail"
    )
    execution_evidence: list[StepEvidence] = Field(default_factory=list)
    environment: EnvironmentSnapshot
    simulator_state: SimulatorStateSnapshot
    mqtt_information: MqttSnapshot | None = Field(default=None)

    @field_validator("execution_id", "test_case_id", "requirement_id")
    @classmethod
    def _ids_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("execution/test_case/requirement ids must not be blank")
        return stripped


# ---------------------------------------------------------------------------
# Batch summary
# ---------------------------------------------------------------------------


class FailureDetail(BaseModel):
    """One line of the summary for tests that did not pass."""

    model_config = {"frozen": True}

    test_case_id: str
    status: TestStatus
    reason: str = Field(default="")
    requirement_id: str = Field(default="")


class ExecutionSummary(BaseModel):
    """Aggregate totals of a batch run, from ACTUAL results only."""

    model_config = {"frozen": True}

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    total_duration: float = Field(default=0.0, ge=0.0)
    pass_rate: float = Field(ge=0.0, description="passed/total*100, 0 when empty")
    failure_details: list[FailureDetail] = Field(default_factory=list)

    @classmethod
    def from_execution_results(cls, results) -> "ExecutionSummary":
        """Aggregate a list of ExecutionResult into one summary."""
        total = len(results)
        passed = sum(1 for r in results if r.status is TestStatus.PASS)
        failed = sum(1 for r in results if r.status is TestStatus.FAIL)
        errors = sum(1 for r in results if r.status is TestStatus.ERROR)
        skipped = sum(1 for r in results if r.status is TestStatus.SKIPPED)
        total_duration = sum(r.duration for r in results)
        pass_rate = round((passed / total) * 100.0, 2) if total else 0.0
        details = [
            FailureDetail(
                test_case_id=r.test_case_id,
                status=r.status,
                reason=r.failure_reason or r.error_message or "",
                requirement_id=r.requirement_id,
            )
            for r in results
            if r.status is not TestStatus.PASS
        ]
        return cls(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            total_duration=total_duration,
            pass_rate=pass_rate,
            failure_details=details,
        )