"""
Phase 8 — the execution service (public API of the test execution engine).

WHY:
    Downstream consumers (reporting, coverage, autonomous refinement) should
    not need to build simulators, injectors, executors, or interpreters. This
    service is the single entry point that turns a Phase 7 `TestCase` into a
    fully traceable `ExecutionResult` / `ExecutionSummary`, with sensible
    defaults and honest behavior on both the happy path and the failure path.

WHAT:
    - execute_action / execute_actions — execute pre-built structured actions.
    - execute_test_case — interpret a Phase 7 TestCase, execute it (isolated
      simulator + injector by default), return a traceable ExecutionResult.
    - execute_test_cases   — batch runner; ONE failing test NEVER stops the
      batch; returns (results, ExecutionSummary).

HOW (honesty / safety):
    - A test whose prose maps to no supported action is an ERROR (never a
      guessed execution).
    - When MQTT actions are involved and no broker is reachable, the default
      policy (`on_mqtt_unavailable="skip"`) converts the execution into an
      honest SKIPPED result — never a fake pass. `on_mqtt_unavailable="error"`
      keeps it an ERROR.
    - Everything is typed; nothing generated is ever executed as code.

HOW TO VERIFY:
    See tests/unit/test_execution_service.py and
    tests/integration/test_execution_full_chain.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.config import Settings
from app.faults.engine import FaultInjector
from app.iot.simulator import TemperatureSensorSimulator
from app.llm.models import TestCase
from app.testing.actions import TestAction
from app.testing.errors import (
    InvalidActionParameterError,
    MalformedTestSpecificationError,
    UnsupportedActionError,
)
from app.testing.executor import TestExecutor, _aggregate_status
from app.testing.interpreter import interpret_test_case
from app.testing.models import (
    EnvironmentSnapshot,
    ExecutionResult,
    ExecutionSummary,
    SimulatorStateSnapshot,
    StepEvidence,
    StepOutcome,
    TestStatus,
)


class ExecutionService:
    """Public entry point for executing structured tests against the simulator."""

    def __init__(
        self,
        *,
        settings_: Settings | None = None,
        make_simulator: Callable[[], TemperatureSensorSimulator] | None = None,
        reset_state_between_tests: bool = True,
        on_mqtt_unavailable: str = "skip",
        max_duration_seconds: float | None = None,
        max_wait_seconds: float | None = None,
    ):
        from app.config import settings as _singleton

        self._settings = settings_ if settings_ is not None else _singleton
        self._make_simulator = make_simulator or (
            lambda: TemperatureSensorSimulator()
        )
        self._reset_state_between_tests = reset_state_between_tests
        if on_mqtt_unavailable not in {"skip", "error"}:
            raise ValueError("on_mqtt_unavailable must be 'skip' or 'error'")
        self._on_mqtt_unavailable = on_mqtt_unavailable
        self._max_duration_seconds = max_duration_seconds
        self._max_wait_seconds = max_wait_seconds

        self._shared_simulator: TemperatureSensorSimulator | None = None
        self._shared_injector = FaultInjector()

    # ------------------------------------------------------------------ public

    def execute_action(
        self,
        action: TestAction,
        *,
        test_case_id: str = "MANUAL",
        requirement_id: str = "NONE",
    ) -> ExecutionResult:
        """Execute a single already-validated action against a default simulator."""
        return self.execute_actions(
            [action], test_case_id=test_case_id, requirement_id=requirement_id
        )

    def execute_actions(
        self,
        actions: list[TestAction],
        *,
        test_case_id: str = "MANUAL",
        requirement_id: str = "NONE",
    ) -> ExecutionResult:
        """Execute a list of actions (state shared within this one run only)."""
        if self._shared_simulator is None:
            self._shared_simulator = self._make_simulator()
        else:
            self._shared_simulator.reset()
        injector = FaultInjector()
        executor = self._new_executor(self._shared_simulator, injector)
        result = executor.execute(
            actions, test_case_id=test_case_id, requirement_id=requirement_id
        )
        return self._finalize_mqtt(result)

    def execute_test_case(
        self,
        test_case: TestCase,
        *,
        interpreter=None,
    ) -> ExecutionResult:
        """Interpret + execute one Phase 7 TestCase with isolated state."""
        try:
            actions = self._interpret(test_case, interpreter)
        except (UnsupportedActionError, InvalidActionParameterError,
                MalformedTestSpecificationError, TypeError) as exc:
            return self._interpretation_error_result(test_case, exc)

        if self._reset_state_between_tests:
            simulator = self._make_simulator()
            injector = FaultInjector()
        else:
            if self._shared_simulator is None:
                self._shared_simulator = self._make_simulator()
            simulator = self._shared_simulator
            injector = self._shared_injector

        executor = self._new_executor(simulator, injector)
        result = executor.execute(
            actions,
            test_case_id=test_case.test_case_id,
            requirement_id=test_case.requirement_id,
        )
        return self._finalize_mqtt(result)

    def execute_test_cases(
        self,
        test_cases,
        *,
        interpreter=None,
    ) -> tuple[list[ExecutionResult], ExecutionSummary]:
        """Run a batch; one failing test never stops the rest of the batch."""
        results: list[ExecutionResult] = []
        for test_case in test_cases:
            results.append(self.execute_test_case(test_case, interpreter=interpreter))
        summary = ExecutionSummary.from_execution_results(results)
        return results, summary

    # ------------------------------------------------------------------ helpers

    def _interpret(self, test_case: TestCase, interpreter=None):
        chosen = interpreter or interpret_test_case
        actions = chosen(test_case)
        if not isinstance(actions, list) or not actions:
            raise MalformedTestSpecificationError(
                "interpretation produced no actions to execute"
            )
        return actions

    @staticmethod
    def _interpretation_error_result(test_case: TestCase, exc: Exception) -> ExecutionResult:
        now = datetime.now(timezone.utc)
        return ExecutionResult(
            test_case_id=test_case.test_case_id,
            requirement_id=test_case.requirement_id,
            status=TestStatus.ERROR,
            started_at=now,
            completed_at=now,
            duration=0.0,
            steps_executed=0,
            steps_passed=0,
            steps_failed=0,
            failure_reason=None,
            error_message=f"{type(exc).__name__}: {exc}",
            execution_evidence=[
                StepEvidence(
                    step_number=1,
                    action="INTERPRETATION_FAILED",
                    action_result=StepOutcome.ERROR,
                    error_message=f"{type(exc).__name__}: {exc}",
                    timestamp=now,
                    duration=0.0,
                )
            ],
            environment=EnvironmentSnapshot(),
            simulator_state=SimulatorStateSnapshot(
                device_name="no-simulator",
                status=None,
                tick_count=0,
                min_temperature_c=0.0,
                max_temperature_c=0.0,
                accuracy_c=0.0,
                seed=0,
            ),
            mqtt_information=None,
        )

    def _new_executor(self, simulator: TemperatureSensorSimulator, injector: FaultInjector) -> TestExecutor:
        return TestExecutor(
            simulator=simulator,
            injector=injector,
            settings_=self._settings,
            max_duration_seconds=self._max_duration_seconds,
            max_wait_seconds=self._max_wait_seconds,
        )

    def _finalize_mqtt(self, result: ExecutionResult) -> ExecutionResult:
        """Honest MQTT handling: no broker reachable -> SKIPPED (or ERROR)."""
        if self._on_mqtt_unavailable != "skip":
            return result

        converted = False
        evidence: list[StepEvidence] = []
        for e in result.execution_evidence:
            if (
                e.action_result is StepOutcome.ERROR
                and e.error_message
                and "unavailable" in e.error_message.lower()
            ):
                converted = True
                e = e.model_copy(update={
                    "action_result": StepOutcome.SKIPPED,
                    "failure_reason": e.error_message,
                    "error_message": None,
                })
            evidence.append(e)

        if not converted:
            return result

        status, reason, error = _aggregate_status(evidence)
        return result.model_copy(update={
            "status": status,
            "failure_reason": reason,
            "error_message": error,
            "execution_evidence": evidence,
            "observed_values": result.observed_values,
            "expected_values": result.expected_values,
            "steps_passed": sum(1 for e in evidence if e.passed),
            "steps_failed": sum(
                1 for e in evidence
                if e.assertion_result is TestStatus.FAIL or e.action_result is StepOutcome.FAIL
            ),
        })