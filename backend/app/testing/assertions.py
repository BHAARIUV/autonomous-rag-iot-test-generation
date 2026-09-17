"""
Phase 8 — safe, deterministic assertion engine.

WHY:
    Assertions are pure, side-effect-free evaluations of "observed vs
    expected". They decide PASS (expectation met) or FAIL (expectation not
    met) — a FAIL is a legitimate, evaluated outcome, never an error. Keeping
    them as pure functions makes them trivially deterministic and testable.

WHAT:
    - `AssertionResult` — structured, frozen outcome of one assertion.
    - `evaluate_value`  — ASSERT_VALUE  : numeric equality within tolerance
                           (or exact string equality).
    - `evaluate_range`  — ASSERT_RANGE  : inclusive [low, high] range check.
    - `evaluate_status` — ASSERT_STATUS : ONLINE/OFFLINE + valid flag check.
    - `evaluate_message`— ASSERT_MESSAGE: MQTT message count / field equality.

HOW TO VERIFY:
    See tests/unit/test_execution_assertions.py.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.iot.models import SensorStatus


class AssertionResult(BaseModel):
    """Structured outcome of one assertion evaluation."""

    model_config = {"frozen": True}

    passed: bool
    kind: str = Field(description="VALUE | RANGE | STATUS | MESSAGE")
    expected: str = Field(default="", description="Human-readable expectation")
    observed: str = Field(default="", description="Human-readable observation")
    detail: str = Field(default="", description="Why it passed or failed")
    asserted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


def _fmt(value) -> str:
    if isinstance(value, float):
        if math.isnan(value):
            return "no value (offline/unavailable)"
        if value == int(value):
            return str(int(value))
        return f"{value:g}"
    if value is None:
        return "no value"
    return str(value)


def evaluate_value(observed, expected, tolerance: float = 1e-6) -> AssertionResult:
    """ASSERT_VALUE: observed must equal expected within `tolerance`.

    Numeric comparison when both can be coerced to floats; exact string
    comparison otherwise. A missing (None) observation fails the assertion.
    """
    expected_s = _fmt(expected)
    observed_s = _fmt(observed)
    if observed is None:
        return AssertionResult(
            passed=False, kind="VALUE", expected=expected_s, observed=observed_s,
            detail="no observed value to compare",
        )
    try:
        diff = abs(float(observed) - float(expected))
    except (TypeError, ValueError):
        passed = str(observed) == str(expected)
        return AssertionResult(
            passed=passed, kind="VALUE", expected=expected_s, observed=observed_s,
            detail="matched" if passed else "values do not match",
        )
    passed = diff <= tolerance
    return AssertionResult(
        passed=passed, kind="VALUE", expected=expected_s, observed=observed_s,
        detail=f"observed {observed_s} vs expected {expected_s} (±{tolerance:g}) — "
               f"{'within tolerance' if passed else 'outside tolerance'}",
    )


def evaluate_range(observed, low: float, high: float) -> AssertionResult:
    """ASSERT_RANGE: observed must satisfy low <= observed <= high (inclusive)."""
    expected_s = f"[{_fmt(low)}, {_fmt(high)}]"
    observed_s = _fmt(observed)
    if observed is None:
        return AssertionResult(
            passed=False, kind="RANGE", expected=expected_s, observed=observed_s,
            detail="no observed value to check",
        )
    try:
        value = float(observed)
    except (TypeError, ValueError):
        return AssertionResult(
            passed=False, kind="RANGE", expected=expected_s, observed=observed_s,
            detail=f"observed value is not numeric: {observed!r}",
        )
    if math.isnan(value):
        return AssertionResult(
            passed=False, kind="RANGE", expected=expected_s, observed=observed_s,
            detail="observed value is NaN (device offline / invalid)",
        )
    passed = low <= value <= high
    return AssertionResult(
        passed=passed, kind="RANGE", expected=expected_s, observed=observed_s,
        detail=f"{observed_s} is {'within' if passed else 'outside'} {expected_s}",
    )


def evaluate_status(
    observed_status: SensorStatus | None,
    observed_valid: bool | None = None,
    *,
    expected_status: SensorStatus | None = None,
    expected_valid: bool | None = None,
) -> AssertionResult:
    """ASSERT_STATUS: compare device status and optional valid flag."""
    expected_parts = []
    if expected_status is not None:
        expected_parts.append(f"status={expected_status.value}")
    if expected_valid is not None:
        expected_parts.append(f"valid={expected_valid}")
    expected_s = " and ".join(expected_parts) or "(no criteria)"
    observed_s = _fmt(observed_status)
    if observed_valid is not None:
        observed_s += f", valid={observed_valid}"

    if expected_status is not None and observed_status is not expected_status:
        return AssertionResult(
            passed=False, kind="STATUS", expected=expected_s, observed=observed_s,
            detail=f"observed status {observed_status.value if observed_status else None} "
                   f"!= expected {expected_status.value}",
        )
    if expected_valid is not None and observed_valid != expected_valid:
        return AssertionResult(
            passed=False, kind="STATUS", expected=expected_s, observed=observed_s,
            detail=f"observed valid={observed_valid} != expected valid={expected_valid}",
        )
    return AssertionResult(
        passed=True, kind="STATUS", expected=expected_s, observed=observed_s,
        detail="status matches expected",
    )


def evaluate_message(
    messages,
    *,
    topic: str | None = None,
    field: str | None = None,
    equals=None,
    min_count: int = 1,
) -> AssertionResult:
    """ASSERT_MESSAGE: at least `min_count` messages match the predicate.

    `messages` is any sequence of objects with attributes (e.g. Phase 3
    `SensorMqttMessage`). Non-numeric `equals` values for `temperature` are
    compared numerically.
    """
    received = list(messages)
    expected_s = f">={min_count} message(s)"
    if topic:
        expected_s += f" on '{topic}'"
    if field is not None:
        expected_s += f" with {field}={_fmt(equals)}"

    if len(received) < min_count:
        return AssertionResult(
            passed=False, kind="MESSAGE", expected=expected_s,
            observed=f"{len(received)} received", detail="not enough messages received",
        )

    matched = received
    if topic:
        matched = [m for m in matched if getattr(m, "topic", m) == topic]
    if field is not None and len(matched) >= min_count:
        matching = []
        for m in matched:
            value = getattr(m, field, None)
            if equals is None:
                ok = value is not None
            else:
                try:
                    ok = abs(float(value) - float(equals)) < 1e-6
                except (TypeError, ValueError):
                    ok = str(value) == str(equals)
            if ok:
                matching.append(m)
        matched = matching

    observed_s = f"{len(matched)} matching of {len(received)} received"
    passed = len(matched) >= min_count
    return AssertionResult(
        passed=passed, kind="MESSAGE", expected=expected_s, observed=observed_s,
        detail=f"found {len(matched)} matching message(s) — "
               f"{'enough' if passed else 'not enough'}",
    )