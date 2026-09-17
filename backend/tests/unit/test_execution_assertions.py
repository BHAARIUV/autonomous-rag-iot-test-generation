"""
Phase 8 unit tests — the pure, deterministic assertion engine.

Covers all four assertion kinds: VALUE, RANGE, STATUS, MESSAGE — including
the inclusive-bound, NaN, missing-observation, and numeric-tolerance cases.
"""

import pytest

from app.iot.models import SensorStatus
from app.testing import assertions
from app.testing.assertions import AssertionResult


# --------------------------------------------------------------------- VALUE


def test_value_numeric_within_tolerance_passes():
    assert assertions.evaluate_value(42.5, 42.500001).passed is True


def test_value_numeric_outside_tolerance_fails():
    r = assertions.evaluate_value(42.5, 42.7, tolerance=0.1)
    assert r.passed is False
    assert r.kind == "VALUE"


def test_value_string_equality():
    assert assertions.evaluate_value("ONLINE", "ONLINE").passed is True
    assert assertions.evaluate_value("ONLINE", "OFFLINE").passed is False


def test_value_missing_observation_fails():
    r = assertions.evaluate_value(None, 25.0)
    assert r.passed is False
    assert "no observed" in r.detail


# --------------------------------------------------------------------- RANGE


def test_range_inclusive_bounds_pass():
    assert assertions.evaluate_range(25.0, -40.0, 125.0).passed is True
    assert assertions.evaluate_range(-40.0, -40.0, 125.0).passed is True
    assert assertions.evaluate_range(125.0, -40.0, 125.0).passed is True


def test_range_outside_fails():
    r = assertions.evaluate_range(125.1, -40.0, 125.0)
    assert r.passed is False
    assert "outside" in r.detail


def test_range_missing_observation_fails():
    assert assertions.evaluate_range(None, -40.0, 125.0).passed is False


def test_range_nan_fails():
    assert assertions.evaluate_range(float("nan"), -40.0, 125.0).passed is False


def test_range_non_numeric_fails():
    assert assertions.evaluate_range("hot", -40.0, 125.0).passed is False


# -------------------------------------------------------------------- STATUS


def test_status_match_passes():
    r = assertions.evaluate_status(
        SensorStatus.ONLINE, True, expected_status=SensorStatus.ONLINE, expected_valid=True
    )
    assert r.passed is True
    assert r.kind == "STATUS"


def test_status_mismatch_fails():
    r = assertions.evaluate_status(SensorStatus.OFFLINE, True, expected_status=SensorStatus.ONLINE)
    assert r.passed is False
    assert "!=" in r.detail


def test_status_valid_flag_mismatch_fails():
    r = assertions.evaluate_status(SensorStatus.ONLINE, False, expected_valid=True)
    assert r.passed is False


def test_status_only_valid_criteria():
    r = assertions.evaluate_status(SensorStatus.ONLINE, False, expected_valid=False)
    assert r.passed is True


# -------------------------------------------------------------------- MESSAGE


def _msg(temperature=None, valid=True, status=SensorStatus.ONLINE):
    from app.iot.mqtt_messages import SensorMqttMessage
    from app.iot.models import utc_epoch_start

    return SensorMqttMessage(
        sensor_id="s1", timestamp=utc_epoch_start(), temperature=temperature,
        status=status, valid=valid,
    )


def test_message_min_count_enough_passes():
    r = assertions.evaluate_message([_msg(), _msg()], min_count=2)
    assert r.passed is True
    assert r.observed == "2 matching of 2 received"


def test_message_min_count_not_enough_fails():
    r = assertions.evaluate_message([_msg()], min_count=2)
    assert r.passed is False
    assert "not enough" in r.detail


def test_message_field_numeric_tolerance():
    r = assertions.evaluate_message([_msg(temperature=42.5)], field="temperature", equals=42.500001)
    assert r.passed is True


def test_message_field_mismatch_fails():
    r = assertions.evaluate_message([_msg(temperature=42.5)], field="temperature", equals=90.0)
    assert r.passed is False


def test_message_field_valid_flag():
    r = assertions.evaluate_message([_msg(valid=True)], field="valid", equals=True)
    assert r.passed is True
    r2 = assertions.evaluate_message([_msg(valid=False)], field="valid", equals=True)
    assert r2.passed is False


def test_message_equals_none_means_field_present():
    r = assertions.evaluate_message([_msg(valid=True)], field="valid", equals=None)
    assert r.passed is True


def test_assertion_result_is_structured_and_frozen():
    r = AssertionResult(passed=True, kind="RANGE", expected="[1, 2]", observed="1.5", detail="in range")
    assert r.expected == "[1, 2]"
    assert r.asserted_at is not None
    with pytest.raises(Exception):
        r.passed = False