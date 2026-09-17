"""
Phase 5 unit tests: TXT / labeled-text parsing (the shared text path for
.txt files, manual text input, and PDF-extracted text).
"""

from app.ingestion.text_parser import parse_spec_text


DEMO = """# temperature sensor
Device: Temperature Sensor
Range: -40 °C to 125 °C
Accuracy: ±0.5 °C
Sampling Interval: 1 second
Communication Protocol: MQTT
"""


def test_demo_spec_all_fields_recognized():
    fields, warnings = parse_spec_text(DEMO, "s.txt", "txt")
    assert warnings == []
    assert {f.key for f in fields} == {
        "device_name",
        "temperature_range",
        "temperature_accuracy",
        "sampling_interval",
        "communication_protocol",
    }


def test_line_numbers_are_one_based():
    fields, _ = parse_spec_text(DEMO, "s.txt", "txt")
    by_key = {f.key: f for f in fields}
    # Line 1 is the '#' comment; fields start on line 2.
    assert by_key["device_name"].source_reference == "line 2"
    assert by_key["temperature_range"].source_reference == "line 3"
    assert by_key["communication_protocol"].source_reference == "line 6"


def test_raw_values_preserved_verbatim():
    fields, _ = parse_spec_text(DEMO, "s.txt", "txt")
    by_key = {f.key: f for f in fields}
    assert by_key["temperature_range"].raw_value == "-40 °C to 125 °C"
    assert by_key["device_name"].raw_value == "Temperature Sensor"


def test_eq_separator_supported():
    fields, warnings = parse_spec_text(
        "Device = Temperature Sensor\nRange = -40 to 125 C",
        "s.txt",
        "txt",
    )
    assert warnings == []
    assert len(fields) == 2


def test_unrecognized_label_warned_not_fabricated():
    text = "Device: Sensor X\nColor: blue\n"
    fields, warnings = parse_spec_text(text, "s.txt", "txt")
    assert len(fields) == 1
    assert fields[0].key == "device_name"
    assert any("Color" in w for w in warnings)


def test_free_form_line_warned_not_fabricated():
    text = "This datasheet describes a wireless temperature sensor.\n"
    fields, warnings = parse_spec_text(text, "s.txt", "txt")
    assert fields == []
    assert len(warnings) == 1


def test_ambiguous_value_flagged_not_guessed():
    text = "Accuracy: high precision\nSampling Interval: 1 second\n"
    fields, warnings = parse_spec_text(text, "s.txt", "txt")
    assert len(fields) == 2
    accuracy = next(f for f in fields if f.key == "temperature_accuracy")
    assert accuracy.parseable is False
    assert accuracy.parsed_value is None
    assert accuracy.ambiguity_note is not None
    assert not any("guessed" in w.lower() for w in warnings)


def test_blank_and_comment_lines_ignored():
    text = "\n\n# comment\n\nDevice: Sensor\n\n"
    fields, warnings = parse_spec_text(text, "s.txt", "txt")
    assert len(fields) == 1
    assert warnings == []


def test_empty_text_yields_no_fields():
    fields, warnings = parse_spec_text("   \n  \n", "s.txt", "txt")
    assert fields == []
    assert warnings == []