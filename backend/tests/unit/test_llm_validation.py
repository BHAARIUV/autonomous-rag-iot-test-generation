"""
Phase 7 unit tests: generated-test validation (rejects malformed LLM output
safely; never silently repairs it).
"""

import pytest

from app.llm.errors import TestValidationError
from app.llm.models import (
    GenerationMetadata,
    SourceContext,
    SourceContextItem,
    TestCase,
    TestCaseCandidate,
    TestCategory,
    TestPriority,
)
from app.llm.validation import (
    candidate_issues,
    raise_for_issues,
    validate_candidates,
)


def _metadata() -> GenerationMetadata:
    return GenerationMetadata(
        provider="mock",
        model="mock-llm",
        generation_mode="mock",
        prompt_version="phase7-v1",
        timestamp="2026-01-01T00:00:00+00:00",
        retrieved_chunk_ids=["c1"],
    )


def _context() -> SourceContext:
    return SourceContext(
        retrieval_query="REQ-001 ...",
        chunks=[
            SourceContextItem(
                chunk_id="c1", document_id="kb-1", source="H", title="T",
                topic="boundary_value_analysis", relevance=0.7,
            )
        ],
    )


def _candidate(**overrides) -> TestCaseCandidate:
    base = dict(
        test_case_id="TC-001",
        requirement_id="REQ-001",
        title="Minimum boundary",
        objective="Verify min bound.",
        category="BOUNDARY",
        priority="HIGH",
        preconditions=["Powered"],
        test_steps=["Drive to -40 C.", "Read report"],
        expected_result="Accepted.",
    )
    base.update(overrides)
    return TestCaseCandidate.model_validate(base)


def test_valid_candidate_has_no_issues():
    assert candidate_issues(_candidate(), expected_requirement_id="REQ-001", seen_test_ids=set()) == []


def test_missing_required_fields_reported():
    issues = candidate_issues(
        _candidate(title="", objective="", expected_result="", test_steps=[]),
        expected_requirement_id="REQ-001",
        seen_test_ids=set(),
    )
    joined = "\n".join(issues)
    assert "title" in joined and "objective" in joined and "expected_result" in joined
    assert "test_steps" in joined


@pytest.mark.parametrize(
    "bad, token",
    [
        ({"category": "MAGIC"}, "invalid category"),
        ({"priority": "URGENT"}, "invalid priority"),
        ({"category": ""}, "missing category"),
        ({"priority": ""}, "missing priority"),
    ],
)
def test_invalid_category_or_priority(bad, token):
    issues = candidate_issues(_candidate(**bad), expected_requirement_id="REQ-001", seen_test_ids=set())
    assert any(token in i for i in issues)


def test_missing_requirement_id():
    issues = candidate_issues(_candidate(requirement_id=""), expected_requirement_id="REQ-001", seen_test_ids=set())
    assert any("missing requirement_id" in i for i in issues)


def test_requirement_id_mismatch():
    issues = candidate_issues(_candidate(requirement_id="REQ-999"), expected_requirement_id="REQ-001", seen_test_ids=set())
    assert any("mismatch" in i for i in issues)


def test_empty_steps_rejected():
    issues = candidate_issues(_candidate(test_steps=[]), expected_requirement_id="REQ-001", seen_test_ids=set())
    assert any("test_steps must not be empty" in i for i in issues)


def test_blank_step_action_rejected():
    issues = candidate_issues(
        _candidate(test_steps=["  ", {"step_number": 2, "action": "ok"}]),
        expected_requirement_id="REQ-001",
        seen_test_ids=set(),
    )
    assert any("empty action" in i for i in issues)


def test_non_sequential_step_numbers_rejected():
    issues = candidate_issues(
        _candidate(test_steps=[{"step_number": 4, "action": "a"}, {"step_number": 9, "action": "b"}]),
        expected_requirement_id="REQ-001",
        seen_test_ids=set(),
    )
    assert any("sequential" in i for i in issues)


def test_duplicate_test_ids_rejected():
    seen: set[str] = set()
    first = _candidate()
    assert candidate_issues(first, expected_requirement_id="REQ-001", seen_test_ids=seen) == []
    seen.add("TC-001")  # simulate a prior case in the same request taking this id
    second = _candidate(title="Different title")
    issues = candidate_issues(second, expected_requirement_id="REQ-001", seen_test_ids=seen)
    assert any("duplicate test_case_id 'TC-001'" in i for i in issues)


def test_bad_test_id_format_rejected():
    issues = candidate_issues(_candidate(test_case_id="not-a-tc"), expected_requirement_id="REQ-001", seen_test_ids=set())
    assert any("TC-###" in i for i in issues)


def test_blank_precondition_reported():
    issues = candidate_issues(_candidate(preconditions=["ok", "   "]), expected_requirement_id="REQ-001", seen_test_ids=set())
    assert any("preconditions" in i for i in issues)


def test_validate_candidates_builds_traceable_test_cases():
    test_cases, issues = validate_candidates(
        [_candidate()],
        expected_requirement_id="REQ-001",
        metadata=_metadata(),
        source_context=_context(),
    )
    assert issues == []
    tc = test_cases[0]
    assert isinstance(tc, TestCase)
    assert tc.requirement_id == "REQ-001"
    assert tc.category is TestCategory.BOUNDARY
    assert tc.priority is TestPriority.HIGH
    assert tc.source_context.chunks[0].chunk_id == "c1"
    assert tc.generation_metadata.retrieved_chunk_ids == ["c1"]


def test_validate_candidates_auto_assigns_sequential_ids():
    cases = [_candidate(test_case_id=""), _candidate(test_case_id="", title="B")]
    test_cases, issues = validate_candidates(
        cases,
        expected_requirement_id="REQ-001",
        metadata=_metadata(),
        source_context=None,
    )
    assert issues == []
    assert [t.test_case_id for t in test_cases] == ["TC-001", "TC-002"]


def test_mixed_valid_and_invalid_keeps_only_valid():
    valid = _candidate(test_case_id="TC-010")
    invalid = _candidate(title="")
    test_cases, issues = validate_candidates(
        [valid, invalid],
        expected_requirement_id="REQ-001",
        metadata=_metadata(),
        source_context=None,
    )
    assert len(test_cases) == 1
    assert test_cases[0].test_case_id == "TC-010"
    assert any("title" in i for i in issues)


def test_raise_for_issues_raises_typed_error():
    with pytest.raises(TestValidationError):
        raise_for_issues(["title missing", "category invalid"])


def test_raise_for_issues_noop_when_clean():
    raise_for_issues([])


def test_uniqueness_across_shared_request_is_enforced():
    tc_a, issues_a = validate_candidates(
        [_candidate(test_case_id="TC-005")],
        expected_requirement_id="REQ-001",
        metadata=_metadata(),
        source_context=None,
        seen_test_ids=set(),
    )
    assert issues_a == []

    seen_shared = set()
    _, _ = validate_candidates(
        [_candidate(test_case_id="TC-005")],
        expected_requirement_id="REQ-001",
        metadata=_metadata(),
        source_context=None,
        seen_test_ids=seen_shared,
    )
    _, issues_b = validate_candidates(
        [_candidate(test_case_id="TC-005")],
        expected_requirement_id="REQ-001",
        metadata=_metadata(),
        source_context=None,
        seen_test_ids=seen_shared,
    )
    assert any("duplicate test_case_id 'TC-005'" in i for i in issues_b)