"""
Phase 5 unit tests: the structured requirement / constraint / field models.
Pure data-model tests — no parsing, no files.
"""

import pytest
from pydantic import ValidationError

from app.ingestion.models import (
    Constraint,
    IngestedSpecification,
    Requirement,
    RequirementCategory,
    RequirementSeverity,
    SpecField,
)


def _req(**overrides) -> Requirement:
    base = {
        "requirement_id": "REQ-001",
        "description": "The device shall do something.",
        "category": RequirementCategory.FUNCTIONAL,
        "source": "manual",
        "source_reference": "line 1",
    }
    base.update(overrides)
    return Requirement(**base)


def test_category_enum_values():
    assert [c.value for c in RequirementCategory] == [
        "FUNCTIONAL",
        "RANGE",
        "ACCURACY",
        "TIMING",
        "COMMUNICATION",
        "DATA_VALIDATION",
        "RELIABILITY",
        "SAFETY",
    ]


def test_severity_enum_values():
    assert [s.value for s in RequirementSeverity] == [
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]


def test_requirement_defaults():
    req = _req()
    assert req.constraints == []
    assert req.severity is RequirementSeverity.MEDIUM
    assert req.normalized is True


def test_requirement_immutable():
    req = _req()
    with pytest.raises(ValidationError):
        req.description = "mutated"


def test_requirement_can_equal_other_normalized():
    # `normalized` is part of the model contract (extractor sets True).
    assert _req().normalized is True


def test_constraint_kind_validated():
    Constraint(kind="min", value="-40", unit="°C")
    Constraint(kind="enum", value="MQTT")
    with pytest.raises(ValidationError):
        Constraint(kind="nonsense", value="x")
    with pytest.raises(ValidationError):
        Constraint(kind="value", value="   ")


def test_constraint_immutable():
    c = Constraint(kind="max", value="125", unit="°C")
    with pytest.raises(ValidationError):
        c.value = "999"


def test_spec_field_can_be_metadata_or_requirement():
    meta = SpecField(
        key="device_name",
        label="Device",
        raw_value="Temperature Sensor",
        parsed_value="Temperature Sensor",
        source_reference="line 1",
        category=None,
        parseable=True,
    )
    assert meta.category is None

    req_field = SpecField(
        key="temperature_range",
        label="Range",
        raw_value="-40 C to 125 C",
        parsed_value="-40 to 125",
        unit="°C",
        components={"min": "-40", "max": "125"},
        source_reference="line 2",
        category=RequirementCategory.RANGE,
    )
    assert req_field.category is RequirementCategory.RANGE
    assert req_field.unit == "°C"


def test_ingested_specification_counts():
    r = _req()
    result = IngestedSpecification(
        source="manual",
        source_format="text",
        requirements=[r],
        warnings=["w"],
    )
    assert result.requirement_count == 1
    assert result.errors == []