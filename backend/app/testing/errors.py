"""
Phase 8 — typed error hierarchy for the test-execution engine.

WHY:
    Generated / interpreted test specifications are UNTRUSTED input. Every
    failure path must be an explicit, typed, catchable error so the
    execution service can turn it into a structured `ExecutionResult`
    (status ERROR or SKIPPED) instead of a bare exception that crashes a
    batch. The FAIL vs ERROR contract is preserved: assertion mismatches
    are results, never exceptions.

HOW:
    - `TestExecutionError` is the common base (project convention, matching
      `app/llm/errors.py` and `app/rag/errors.py`).
    - `UnknownActionError`         — an action type that is not supported.
    - `UnsupportedActionError`     — test-step prose that maps to no
      supported structured action (rejected safely).
    - `InvalidActionParameterError`— params are wrong type / missing /
      out of allowed range (e.g. a WAIT longer than the cap).
    - `MalformedTestSpecificationError` — test case object is not usable.
    - `ExecutionTimeoutError`      — the per-test wall-clock budget expired.
    - `SimulatorUnavailableError`  — a simulator action ran without a device.
    - `MqttUnavailableError`       — broker unreachable / not connected.
    - `FaultUnavailableError`      — fault registration/injection failed.
    - `AssertionEvaluationError`   — an assertion could not be evaluated
      (evaluated-but-failed assertions are NOT errors).
"""

from __future__ import annotations


class TestExecutionError(Exception):
    """Base class for every Phase 8 execution error."""


class UnknownActionError(TestExecutionError):
    """An action type that is not in the supported set."""


class UnsupportedActionError(TestExecutionError):
    """Test content maps to no supported structured action (rejected safely)."""


class InvalidActionParameterError(TestExecutionError):
    """Action parameters are missing, wrong-typed, or out of allowed range."""


class MalformedTestSpecificationError(TestExecutionError):
    """The test case / specification object cannot be executed as written."""


class ExecutionTimeoutError(TestExecutionError):
    """The per-test wall-clock budget was exceeded."""


class SimulatorUnavailableError(TestExecutionError):
    """A simulator action was requested but no simulator is available."""


class MqttUnavailableError(TestExecutionError):
    """An MQTT action was requested but the broker is unreachable/disconnected."""


class FaultUnavailableError(TestExecutionError):
    """A fault could not be registered or activated."""


class AssertionEvaluationError(TestExecutionError):
    """An assertion call could not evaluate its inputs."""