"""
Phase 5 unit tests: the field registry and the strict value parsers
(RANGE / TOLERANCE / DURATION / NUMBER_UNIT / STRING).
"""

from app.ingestion.fields import (
    FIELD_REGISTRY,
    ValueKind,
    field_for_key,
    parse_duration,
    parse_field_value,
    parse_number_unit,
    parse_range,
    parse_string,
    parse_tolerance,
)
from app.ingestion.models import RequirementCategory


def test_registry_covers_all_required_categories():
    categories = {fdef.category for fdef in FIELD_REGISTRY if fdef.category}
    required = {
        RequirementCategory.FUNCTIONAL,
        RequirementCategory.RANGE,
        RequirementCategory.ACCURACY,
        RequirementCategory.TIMING,
        RequirementCategory.COMMUNICATION,
        RequirementCategory.DATA_VALIDATION,
        RequirementCategory.RELIABILITY,
        RequirementCategory.SAFETY,
    }
    assert required.issubset(categories)


def test_field_for_key_is_alias_insensitive():
    assert field_for_key("Range").key == "temperature_range"
    assert field_for_key("temperature range").key == "temperature_range"
    assert field_for_key("Temperature-Range").key == "temperature_range"
    assert field_for_key("accuracy").key == "temperature_accuracy"
    assert field_for_key("communication protocol").key == "communication_protocol"
    assert field_for_key("unknown thing") is None


def test_parse_range_deg_c_to_form():
    pv = parse_range("-40 °C to 125 °C")
    assert pv is not None
    assert pv.value == "-40 to 125"
    assert pv.unit == "°C"
    assert pv.components == {"min": "-40", "max": "125"}


def test_parse_range_plain_numbers():
    pv = parse_range("0 to 100")
    assert pv is not None
    assert pv.unit is None
    assert pv.components == {"min": "0", "max": "100"}


def test_parse_range_comma_form():
    pv = parse_range("[-40, 125] C")
    assert pv is not None
    assert pv.value == "-40 to 125"
    assert pv.unit == "°C"


def test_parse_range_negative_second_value():
    pv = parse_range("-40 to -10")
    assert pv is not None
    assert pv.components == {"min": "-40", "max": "-10"}


def test_parse_range_inverted_rejected_as_ambiguous():
    # Reversed bounds are ambiguous, not guessed.
    assert parse_range("125 to -40") is None


def test_parse_range_garbage_rejected():
    assert parse_range("wide") is None
    assert parse_range("") is None
    assert parse_range("a bunch of text") is None


def test_parse_tolerance_pm_sign():
    pv = parse_tolerance("±0.5 °C")
    assert pv is not None
    assert pv.value == "0.5"
    assert pv.unit == "°C"
    assert pv.note is None


def test_parse_tolerance_plus_minus_slash():
    pv = parse_tolerance("+/-0.5 C")
    assert pv is not None
    assert pv.value == "0.5"
    assert pv.unit == "°C"


def test_parse_tolerance_without_sign_is_flagged_not_guessed():
    pv = parse_tolerance("0.5 C")
    assert pv is not None
    assert pv.value == "0.5"
    assert pv.note is not None  # transparency note about implied +/-


def test_parse_tolerance_garbage_rejected():
    assert parse_tolerance("high precision") is None


def test_parse_duration_units():
    assert parse_duration("1 second").unit == "s"
    assert parse_duration("1 s").unit == "s"
    assert parse_duration("24 months").value == "24"
    assert parse_duration("500 ms").unit == "ms"
    assert parse_duration("thirty") is None


def test_parse_number_unit():
    pv = parse_number_unit("3.3 V")
    assert pv.value == "3.3"
    assert pv.unit == "V"
    pv = parse_number_unit("1 Hz")
    assert pv.unit == "Hz"
    assert parse_number_unit("no numbers here") is None


def test_parse_string_keeps_explicit_text():
    pv = parse_string("MQTT")
    assert pv.value == "MQTT"
    assert pv.components == {"value": "MQTT"}
    assert parse_string("   ") is None


def test_parse_field_value_dispatches_by_kind():
    assert parse_field_value(ValueKind.STRING, "JSON").value == "JSON"
    assert parse_field_value(ValueKind.RANGE, "-40 to 125").components == {
        "min": "-40",
        "max": "125",
    }
    assert parse_field_value(ValueKind.TOLERANCE, "±0.5 C").value == "0.5"
    assert parse_field_value(ValueKind.DURATION, "1 second").unit == "s"
    assert parse_field_value(ValueKind.NUMBER_UNIT, "3.3 V").unit == "V"
    assert parse_field_value(ValueKind.RANGE, "??") is None