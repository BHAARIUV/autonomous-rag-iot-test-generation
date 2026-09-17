"""
Phase 5 unit tests: the end-to-end ingestion service — TXT / JSON / PDF /
manual dispatch, missing fields, invalid input, empty input, ambiguity
flagging, and source traceability.
"""

import json

import pytest

from app.ingestion.errors import (
    EmptySpecificationError,
    SpecificationParseError,
    UnreadableFileError,
    UnsupportedFormatError,
)
from app.ingestion.models import (
    RequirementCategory,
    RequirementSeverity,
)
from app.ingestion.service import ingest_specification, ingest_text

from tests.unit._pdf_helpers import build_pdf

DEMO = """Device: Temperature Sensor
Range: -40 °C to 125 °C
Accuracy: ±0.5 °C
Sampling Interval: 1 second
Communication Protocol: MQTT
"""


# ---------------------------------------------------------------- manual / text

def test_manual_text_demo_exact_requirements():
    result = ingest_text(DEMO, source="manual")
    assert result.source == "manual"
    assert result.source_format == "text"
    assert result.errors == []
    assert result.warnings == []
    assert len(result.requirements) == 4

    r1 = result.requirements[0]
    assert r1.requirement_id == "REQ-001"
    assert r1.category is RequirementCategory.RANGE
    assert r1.source == "manual"
    assert r1.source_reference == "line 2"
    assert [(c.kind, c.value, c.unit) for c in r1.constraints] == [
        ("min", "-40", "°C"),
        ("max", "125", "°C"),
    ]


def test_manual_text_traceability_each_requirement():
    result = ingest_text(DEMO, source="air-quality.txt")
    refs = [r.source_reference for r in result.requirements]
    assert refs == ["line 2", "line 3", "line 4", "line 5"]
    assert all(r.source == "air-quality.txt" for r in result.requirements)


def test_manual_text_without_source_defaults_to_manual():
    result = ingest_text(DEMO)
    assert result.source == "manual"


def test_manual_text_lists_detected_fields_for_audit():
    result = ingest_text(DEMO)
    assert {f.key for f in result.fields} == {
        "device_name",
        "temperature_range",
        "temperature_accuracy",
        "sampling_interval",
        "communication_protocol",
    }


# ---------------------------------------------------------------------- files

def test_txt_file_ingestion_and_exportable_result(tmp_path):
    path = tmp_path / "sensor.txt"
    path.write_text(DEMO, encoding="utf-8")
    result = ingest_specification(path)
    assert result.source_format == "txt"
    assert result.source == str(path)
    assert len(result.requirements) == 4
    # Results are JSON-serializable for later persistence.
    payload = json.loads(result.model_dump_json())
    assert payload["source_format"] == "txt"
    assert payload["requirements"][0]["requirement_id"] == "REQ-001"


def test_json_file_ingestion(tmp_path):
    path = tmp_path / "sensor.json"
    path.write_text(
        json.dumps(
            {
                "temperature_range": {"min": -40, "max": 125, "unit": "C"},
                "communication_protocol": "MQTT",
            }
        ),
        encoding="utf-8",
    )
    result = ingest_specification(path)
    assert result.source_format == "json"
    assert len(result.requirements) == 2
    assert result.requirements[0].source_reference == "$.temperature_range"


def test_pdf_file_ingestion(tmp_path):
    path = tmp_path / "sensor.pdf"
    path.write_bytes(build_pdf([DEMO]))
    result = ingest_specification(path)
    assert result.source_format == "pdf"
    assert len(result.requirements) == 4
    assert result.requirements[0].source_reference.startswith("page 1")


# ------------------------------------------------------- missing / ambiguity

def test_missing_fields_flagged_as_incomplete():
    text = "Device: Temperature Sensor\nCommunication Protocol: MQTT\n"
    result = ingest_text(text, source="s.txt")
    assert result.errors == []
    warning_text = " ".join(result.warnings).lower()
    assert "incomplete" in warning_text
    assert "temperature range" in warning_text


def test_ambiguous_value_flagged_no_silent_guess():
    text = "Accuracy: very precise\nRange: -40 to 125 C\n"
    result = ingest_text(text, source="s.txt")
    assert len(result.requirements) == 1
    warning_text = " ".join(result.warnings).lower()
    assert "accuracy" in warning_text
    assert any("guess" in w or "skipped" in w for w in result.warnings)


def test_no_recognized_fields_reported_as_error():
    result = ingest_text("Just some description text.\n", source="s.txt")
    assert result.requirements == []
    assert any("no recognized" in e.lower() for e in result.errors)


# ------------------------------------------------------------------ failures

def test_empty_input_raises():
    with pytest.raises(EmptySpecificationError):
        ingest_text("")
    with pytest.raises(EmptySpecificationError):
        ingest_text("   \n  \n")


def test_empty_txt_file_raises(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(EmptySpecificationError):
        ingest_specification(path)


def test_invalid_json_file_raises(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ not valid json !!!", encoding="utf-8")
    with pytest.raises(SpecificationParseError):
        ingest_specification(path)


def test_json_list_root_raises(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SpecificationParseError):
        ingest_specification(path)


def test_unsupported_format_raises(tmp_path):
    path = tmp_path / "spec.docx"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        ingest_specification(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(UnreadableFileError):
        ingest_specification(tmp_path / "nope.txt")


def test_binary_garbage_as_txt_raises_or_errors(tmp_path):
    path = tmp_path / "garbage.txt"
    path.write_bytes(b"\x00\x01\xff\xfe")
    with pytest.raises(SpecificationParseError):
        ingest_specification(path)


# ---------------------------------------------------------------- severities

def test_severity_assignment_from_field_def():
    result = ingest_text(
        "Overheat Protection: 135 C\nBattery Lifetime: 24 months\n",
        source="s.txt",
    )
    by_id = {r.requirement_id: r for r in result.requirements}
    assert by_id["REQ-001"].severity is RequirementSeverity.HIGH
    assert by_id["REQ-002"].severity is RequirementSeverity.LOW