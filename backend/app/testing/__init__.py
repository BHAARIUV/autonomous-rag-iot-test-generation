"""
Phase 8 — IoT Test Execution Engine.

A safe, deterministic execution layer that runs Phase 7 generated test
specifications against the existing simulated IoT environment (Phase 2
simulator, Phase 3 MQTT, Phase 4 faults) WITHOUT ever executing generated
content as code. Test steps are translated by `interpreter.py` into the
closed `TestAction` set, executed by `executor.py`, and aggregated by
`service.py` into fully traceable, typed `ExecutionResult`s.

Preview:
    from app.testing import ExecutionService, TestActionType, make_action

    service = ExecutionService()
    result = service.execute_action(make_action(TestActionType.READ_SENSOR))
    print(result.status)   # PASS / FAIL / ERROR / SKIPPED
"""

from app.testing.actions import (
    PARAM_MODEL_BY_ACTION,
    TestAction,
    TestActionType,
    make_action,
    validate_action,
)
from app.testing.assertions import (
    AssertionResult,
    evaluate_message,
    evaluate_range,
    evaluate_status,
    evaluate_value,
)
from app.testing.errors import (
    AssertionEvaluationError,
    ExecutionTimeoutError,
    FaultUnavailableError,
    InvalidActionParameterError,
    MalformedTestSpecificationError,
    MqttUnavailableError,
    SimulatorUnavailableError,
    TestExecutionError,
    UnknownActionError,
    UnsupportedActionError,
)
from app.testing.executor import TestExecutor
from app.testing.interpreter import interpret_step, interpret_test_case
from app.testing.models import (
    EnvironmentSnapshot,
    ExecutionResult,
    ExecutionSummary,
    FailureDetail,
    MqttSnapshot,
    SensorMqttView,
    SimulatorStateSnapshot,
    StepEvidence,
    StepOutcome,
    TestStatus,
)
from app.testing.service import ExecutionService

__all__ = [
    # actions
    "TestActionType",
    "TestAction",
    "make_action",
    "validate_action",
    "PARAM_MODEL_BY_ACTION",
    # assertions
    "AssertionResult",
    "evaluate_value",
    "evaluate_range",
    "evaluate_status",
    "evaluate_message",
    # errors
    "TestExecutionError",
    "UnknownActionError",
    "UnsupportedActionError",
    "InvalidActionParameterError",
    "MalformedTestSpecificationError",
    "ExecutionTimeoutError",
    "SimulatorUnavailableError",
    "MqttUnavailableError",
    "FaultUnavailableError",
    "AssertionEvaluationError",
    # models
    "TestStatus",
    "StepOutcome",
    "StepEvidence",
    "SimulatorStateSnapshot",
    "SensorMqttView",
    "MqttSnapshot",
    "EnvironmentSnapshot",
    "ExecutionResult",
    "FailureDetail",
    "ExecutionSummary",
    # interpreter
    "interpret_step",
    "interpret_test_case",
    # executor
    "TestExecutor",
    # service
    "ExecutionService",
]