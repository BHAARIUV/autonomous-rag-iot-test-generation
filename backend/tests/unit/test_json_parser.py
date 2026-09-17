"""
Phase 5 unit tests: JSON specification parsing — canonical structure,
nested containers, camelCase keys, structured values, and unknown keys.
"""

import pytest

from app.ingestion.errors import SpecificationParseError
from app.ingestion.json_parser import parse_spec_json, snake_case_key


def test_camel_case_to_snake_case():
    assert snake_case_key("communicationProtocol") == "communication_protocol"
    assert snake_case_key("temperatureRange") == "temperature_range"
    assert snake_case_key("ipRating") == "ip_rating"


def test_structured_range_value_assembled():
    data = {
        "specification": {
            "temperature_range": {"min": -40, "max": 125, "unit": "C"}
        }
    }
    fields, warnings = parse_spec_json(data, "s.json", "json")
    assert warnings == []
    field = fields[0]
    assert field.key == "temperature_range"
    assert field.parsed_value == "-40 to 125"
    assert field.unit == "°C"
    assert field.source_reference == "$.specification.temperature_range"


def test_scalar_string_fields():
    data = {"communication_protocol": "MQTT", "data_format": "JSON"}
    fields, warnings = parse_spec_json(data, "s.json", "json")
    assert warnings == []
    by_key = {f.key: f for f in fields}
    assert by_key["communication_protocol"].parsed_value == "MQTT"
    assert by_key["data_format"].parsed_value == "JSON"


def test_nested_unknown_container_recurse():
    data = {"device": {"name": "Temperature Sensor", "model": "DS-1007E"}}
    fields, warnings = parse_spec_json(data, "s.json", "json")
    assert any(f.key == "device_name" for f in fields)
    assert warnings == []


def test_tolerance_with_sigil_in_json():
    data = {
        "temperature_accuracy": {"value": 0.5, "tolerance": "+/-", "unit": "C"}
    }
    fields, warnings = parse_spec_json(data, "s.json", "json")
    assert warnings == []
    assert fields[0].parsed_value == "0.5"
    assert fields[0].unit == "°C"


def test_duration_in_json():
    data = {"sampling_interval": {"value": 1, "unit": "s"}}
    fields, _ = parse_spec_json(data, "s.json", "json")
    assert fields[0].unit == "s"
    assert fields[0].components == {"value": "1"}


def test_unknown_keys_are_warned_not_fabricated():
    data = {"temperature_range": "-40 to 125 C", "wifi_password": "hunter2"}
    fields, warnings = parse_spec_json(data, "s.json", "json")
    assert len(fields) == 1
    assert any("wifi_password" in w for w in warnings)


def test_ambiguous_json_value_flagged():
    data = {"temperature_accuracy": {"value": "excellent"}}
    fields, warnings = parse_spec_json(data, "s.json", "json")
    assert len(fields) == 1
    assert fields[0].parseable is False
    assert fields[0].parsed_value is None


def test_non_dict_json_rejected():
    with pytest.raises(SpecificationParseError):
        parse_spec_json([], "s.json", "json")
    with pytest.raises(SpecificationParseError):
        parse_spec_json("nope", "s.json", "json")