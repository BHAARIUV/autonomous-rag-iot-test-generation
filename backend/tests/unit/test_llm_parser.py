"""
Phase 7 unit tests: structured-output parsing of raw LLM responses.
"""

import json

import pytest

from app.llm.errors import ResponseParseError
from app.llm.parser import parse_test_cases

VALID_CASE = {
    "test_case_id": "TC-001",
    "requirement_id": "REQ-001",
    "title": "Minimum boundary value",
    "objective": "Verify the minimum boundary value is accepted.",
    "category": "BOUNDARY",
    "priority": "HIGH",
    "preconditions": ["Device powered"],
    "test_steps": ["Drive input to -40 C.", {"step_number": 2, "action": "Read the report."}],
    "expected_result": "Device accepts the value.",
    "test_data": {"inputs": {"temperature": "-40"}, "expected": {"status": "VALID"}},
}


def _payload(test_cases):
    return {"summary": "generated", "test_cases": test_cases}


def test_parse_valid_payload():
    candidates = parse_test_cases(json.dumps(_payload([VALID_CASE])))
    assert len(candidates) == 1
    assert candidates[0].requirement_id == "REQ-001"
    assert candidates[0].category == "BOUNDARY"
    # mixed plain-string and structured steps are preserved
    assert candidates[0].test_steps[0] == "Drive input to -40 C."
    assert candidates[0].test_steps[1].step_number == 2


def test_parse_accepts_fenced_markdown_json():
    raw = f"```json\n{json.dumps(_payload([VALID_CASE]))}\n```"
    assert len(parse_test_cases(raw)) == 1


def test_parse_multiple_cases_preserved_in_order():
    second = dict(VALID_CASE, test_case_id="TC-002", title="Maximum")
    candidates = parse_test_cases(json.dumps(_payload([VALID_CASE, second])))
    assert [c.test_case_id for c in candidates] == ["TC-001", "TC-002"]


def test_parse_empty_response_raises():
    with pytest.raises(ResponseParseError):
        parse_test_cases("")
    with pytest.raises(ResponseParseError):
        parse_test_cases("   ")


def test_parse_not_json_raises():
    with pytest.raises(ResponseParseError):
        parse_test_cases("Here are the tests: TC-001 ...")


def test_parse_bare_string_list_raises():
    with pytest.raises(ResponseParseError):
        parse_test_cases('{"test_cases": "not a list"}')


def test_parse_missing_test_cases_key_raises():
    with pytest.raises(ResponseParseError):
        parse_test_cases('{"fizz": "buzz"}')


def test_parse_empty_test_cases_array_raises():
    with pytest.raises(ResponseParseError):
        parse_test_cases(json.dumps(_payload([])))


def test_parse_extra_keys_ignored():
    raw = json.dumps({**_payload([VALID_CASE]), "unexpected": 123})
    assert len(parse_test_cases(raw)) == 1


def test_parse_top_level_non_object_raises():
    with pytest.raises(ResponseParseError):
        parse_test_cases("[1,2,3]")


def test_unknown_test_data_keys_rejected_at_parse():
    bad = dict(VALID_CASE, test_data={"not_an_allowed_key": "x"})
    with pytest.raises(ResponseParseError):
        parse_test_cases(json.dumps(_payload([bad])))