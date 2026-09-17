"""
Phase 5 unit tests: requirement extraction — ids, categories, constraints,
metadata exclusion, ambiguity handling, and source traceability.
"""

from app.ingestion.extractor import build_requirement, extract_requirements, id_for_index
from app.ingestion.fields import FIELD_REGISTRY, field_for_key, parse_field_value
from app.ingestion.json_parser import parse_spec_json
from app.ingestion.models import RequirementCategory, RequirementSeverity, SpecField
from app.ingestion.text_parser import parse_spec_text


DEMO = """Device: Temperature Sensor
Range: -40 °C to 125 °C
Accuracy: ±0.5 °C
Sampling Interval: 1 second
Communication Protocol: MQTT
"""


def _parse_and_extract(text, source="demo.txt", fmt="txt"):
    fields, p_warnings = parse_spec_text(text, source, fmt)
    reqs, e_warnings = extract_requirements(fields, source, fmt)
    return reqs, p_warnings + e_warnings


def test_demo_produces_exact_four_requirements_in_order():
    reqs, warnings = _parse_and_extract(DEMO)
    assert reqs and warnings == []
    assert [r.requirement_id for r in reqs] == [
        "REQ-001",
        "REQ-002",
        "REQ-003",
        "REQ-004",
    ]
    assert [r.category for r in reqs] == [
        RequirementCategory.RANGE,
        RequirementCategory.ACCURACY,
        RequirementCategory.TIMING,
        RequirementCategory.COMMUNICATION,
    ]


def test_requirement_ids_sequential_from_each_field():
    text = "Accuracy: 0.5 C\nRange: -40 to 125 C\nSampling Interval: 2 s\n"
    reqs, _ = _parse_and_extract(text)
    # First requirement-producing field in source order gets REQ-001.
    assert reqs[0].requirement_id == "REQ-001"
    assert reqs[0].category is RequirementCategory.ACCURACY
    assert reqs[2].requirement_id == "REQ-003"
    assert reqs[2].category is RequirementCategory.TIMING


def test_device_name_is_metadata_not_a_requirement():
    reqs, _ = _parse_and_extract(DEMO)
    assert len(reqs) == 4
    assert all(r.requirement_id in {"REQ-001", "REQ-002", "REQ-003", "REQ-004"}
               for r in reqs)


def test_constraints_are_built_with_units():
    reqs, _ = _parse_and_extract(DEMO)
    by_id = {r.requirement_id: r for r in reqs}
    range_constr = by_id["REQ-001"].constraints
    assert [(c.kind, c.value, c.unit) for c in range_constr] == [
        ("min", "-40", "°C"),
        ("max", "125", "°C"),
    ]
    acc_constr = by_id["REQ-002"].constraints
    assert (acc_constr[0].kind, acc_constr[0].value, acc_constr[0].unit) == (
        "value",
        "0.5",
        "°C",
    )
    comm = by_id["REQ-004"].constraints[0]
    assert comm.kind == "enum" and comm.value == "MQTT"


def test_ambiguous_field_skipped_with_warning_no_id_gap():
    text = (
        "Range: -40 to 125 C\n"
        "Accuracy: wonder-quality\n"
        "Sampling Interval: 1 second\n"
    )
    reqs, warnings = _parse_and_extract(text)
    # The ambiguous accuracy is skipped; ids stay sequential.
    assert [r.requirement_id for r in reqs] == ["REQ-001", "REQ-002"]
    assert [r.category for r in reqs] == [
        RequirementCategory.RANGE,
        RequirementCategory.TIMING,
    ]
    assert any("Accuracy" in w and "skipped" in w for w in warnings)


def test_no_requirements_from_unrecognized_input():
    reqs, warnings = _parse_and_extract("Some random prose about a device.\n")
    assert reqs == []
    assert len(warnings) == 1


def test_source_traceability_is_exact():
    reqs, _ = _parse_and_extract(DEMO, source="my_sensor.txt", fmt="txt")
    for r in reqs:
        assert r.source == "my_sensor.txt"
    assert reqs[0].source_reference == "line 2"
    assert reqs[1].source_reference == "line 3"


def test_build_requirement_renders_normalized_description():
    fdef = field_for_key("temperature_range")
    pv = parse_field_value(fdef.kind, "-40 °C to 125 °C")
    field = SpecField(
        key=fdef.key,
        label="Range",
        raw_value="-40 °C to 125 °C",
        parsed_value=pv.value,
        unit=pv.unit,
        components=pv.components,
        source_reference="line 4",
        category=fdef.category,
        parseable=True,
    )
    req = build_requirement(field, fdef, "REQ-999", "s.txt", "txt")
    assert req.requirement_id == "REQ-999"
    assert req.description == (
        "The device shall measure temperatures within the range "
        "-40 °C to 125 °C."
    )
    assert req.normalized is True
    assert req.severity is RequirementSeverity.MEDIUM


def test_safety_field_gets_high_severity():
    text = "Overheat Protection: 135 °C\n"
    reqs, _ = _parse_and_extract(text)
    assert reqs[0].category is RequirementCategory.SAFETY
    assert reqs[0].severity is RequirementSeverity.HIGH


def test_parity_txt_and_json_extraction_match():
    txt = """Device: Temperature Sensor
Range: -40 C to 125 C
Accuracy: ±0.5 C
Sampling Interval: 1 s
Communication Protocol: MQTT
"""
    json_data = {
        "temperature_range": {"min": -40, "max": 125, "unit": "C"},
        "temperature_accuracy": {"value": 0.5, "tolerance": "±", "unit": "C"},
        "sampling_interval": {"value": 1, "unit": "s"},
        "communication_protocol": "MQTT",
    }
    txt_reqs, _ = _parse_and_extract(txt, "s.a", "txt")
    json_fields, _ = parse_spec_json(json_data, "s.b", "json")
    json_reqs, _ = extract_requirements(json_fields, "s.b", "json")

    assert len(txt_reqs) == len(json_reqs) == 4
    for a, b in zip(txt_reqs, json_reqs):
        assert a.description == b.description
        assert a.category == b.category
        assert [(c.kind, c.value, c.unit) for c in a.constraints] == [
            (c.kind, c.value, c.unit) for c in b.constraints
        ]


def test_id_for_index():
    assert id_for_index(1) == "REQ-001"
    assert id_for_index(12) == "REQ-012"