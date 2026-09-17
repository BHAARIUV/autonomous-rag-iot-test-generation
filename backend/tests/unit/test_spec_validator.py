"""
Phase 5 unit tests: requirement validation — ids, traceability fields,
constraint kinds, and sequential uniqueness.
"""

from app.ingestion.models import Requirement, RequirementCategory, RequirementSeverity
from app.ingestion.validator import validate_requirement, validate_requirements


def _req(**overrides) -> Requirement:
    base = {
        "requirement_id": "REQ-001",
        "description": "The device shall do something.",
        "category": RequirementCategory.FUNCTIONAL,
        "source": "s.txt",
        "source_reference": "line 1",
    }
    base.update(overrides)
    return Requirement(**base)


def test_valid_requirement_has_no_issues():
    assert validate_requirement(_req()) == []


def test_bad_id_format_detected():
    issues = validate_requirement(_req(requirement_id="REQ-1"))
    assert any("REQ-###" in i for i in issues)


def test_missing_traceability_detected():
    issues = validate_requirement(_req(source="", source_reference=""))
    assert any("source" in i and "empty" in i for i in issues)
    assert any("source_reference" in i and "empty" in i for i in issues)


def test_blank_description_detected():
    issues = validate_requirement(_req(description="   "))
    assert any("description is empty" in i for i in issues)


def test_sequence_detected():
    reqs = [_req(), _req(requirement_id="REQ-002")]
    issues = validate_requirements(reqs)
    # REQ-001 is at position 1 (ok), REQ-002 at position 2 is ok.
    assert issues == []


def test_out_of_sequence_detected():
    reqs = [_req(), _req(requirement_id="REQ-003")]
    issues = validate_requirements(reqs)
    assert any("REQ-003" in i and "REQ-002" in i for i in issues)


def test_duplicate_ids_detected():
    reqs = [_req(), _req(requirement_id="REQ-002"), _req(requirement_id="REQ-002")]
    issues = validate_requirements(reqs)
    assert sum("duplicate" in i for i in issues) == 1


def test_unexpected_but_valid_severity_not_an_issue():
    assert validate_requirement(
        _req(severity=RequirementSeverity.CRITICAL)
    ) == []