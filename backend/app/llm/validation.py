"""
Validation layer for generated test cases.

WHAT:
    Takes the loose `TestCaseCandidate` values produced by the parser and
    either converts them into strict `TestCase` records or rejects them
    with a `TestValidationError` listing every problem found.

WHY:
    "Malformed LLM output must fail safely." We never silently repair
    hallucinated content into valid tests. Validation covers:
      - requirement_id present and matching the requirement being generated
      - test_case_id format and uniqueness within the generation request
      - required fields present (title, objective, expected_result)
      - test_steps non-empty, sequential 1-based numbering
      - category and priority drawn from the supported enums
      - preconditions/assumptions are non-blank strings

HOW:
    `validate_candidates(...)` builds final frozen `TestCase` records with
    the RAG source context and generation metadata attached, and returns
    `(test_cases, issues)`. The service raises `TestValidationError` when
    any issue is present.

HOW TO VERIFY:
    See tests/unit/test_llm_validation.py.
"""

from __future__ import annotations

import re

from app.llm.errors import TestValidationError
from app.llm.models import (
    GenerationMetadata,
    SourceContext,
    TestCase,
    TestCaseCandidate,
    TestCategory,
    TestPriority,
    TestStep,
)

_ID_RE = re.compile(r"^TC-\d{3,}$")

_CATEGORY_VALUES = {c.value for c in TestCategory}
_PRIORITY_VALUES = {p.value for p in TestPriority}


def candidate_issues(
    candidate: TestCaseCandidate,
    *,
    expected_requirement_id: str,
    seen_test_ids: set[str],
) -> list[str]:
    """Return the list of validation issues for one candidate ([] = valid)."""
    issues: list[str] = []
    label = (candidate.requirement_id or expected_requirement_id or "(no requirement)")

    rid = (candidate.requirement_id or "").strip()
    if not rid:
        issues.append("test case is missing requirement_id")
    elif rid != expected_requirement_id:
        issues.append(
            f"requirement_id mismatch: candidate refers to '{rid}' but the "
            f"generation run is for '{expected_requirement_id}'"
        )

    if not (candidate.title or "").strip():
        issues.append(f"{label}: test case is missing title")
    if not (candidate.objective or "").strip():
        issues.append(f"{label}: test case is missing objective")

    category = (candidate.category or "").strip().upper()
    if not category:
        issues.append(f"{label}: test case is missing category")
    elif category not in _CATEGORY_VALUES:
        issues.append(
            f"{label}: invalid category '{candidate.category}'; "
            f"expected one of {sorted(_CATEGORY_VALUES)}"
        )

    priority = (candidate.priority or "").strip().upper()
    if not priority:
        issues.append(f"{label}: test case is missing priority")
    elif priority not in _PRIORITY_VALUES:
        issues.append(
            f"{label}: invalid priority '{candidate.priority}'; "
            f"expected one of {sorted(_PRIORITY_VALUES)}"
        )

    if not candidate.test_steps:
        issues.append(f"{label}: test_steps must not be empty")
    else:
        numbers: list[int] = []
        for index, step in enumerate(candidate.test_steps, start=1):
            if isinstance(step, TestStep):
                action = step.action.strip()
                number = step.step_number
            elif isinstance(step, str):
                action = step.strip()
                number = index
            else:  # pragma: no cover - pydantic union handles all cases
                action = ""
                number = -1
            if not action:
                issues.append(f"{label}: step {number} has an empty action")
            numbers.append(number)
        if numbers != list(range(1, len(numbers) + 1)):
            issues.append(
                f"{label}: test step numbers must be sequential 1..{len(numbers)}, "
                f"got {numbers}"
            )

    if not (candidate.expected_result or "").strip():
        issues.append(f"{label}: test case is missing expected_result")

    for field_name, values in (
        ("preconditions", candidate.preconditions),
        ("assumptions", candidate.assumptions),
    ):
        for value in values or []:
            if not (value or "").strip():
                issues.append(f"{label}: {field_name} contains a blank entry")

    tid = (candidate.test_case_id or "").strip()
    if tid:
        if not _ID_RE.match(tid):
            issues.append(f"test_case_id '{tid}' must match the pattern TC-###")
        elif tid in seen_test_ids:
            issues.append(f"duplicate test_case_id '{tid}' within the generation request")

    return issues


def validate_candidates(
    candidates: list[TestCaseCandidate],
    *,
    expected_requirement_id: str,
    metadata: GenerationMetadata,
    source_context: SourceContext | None,
    auto_assign_ids: bool = True,
    auto_start: int = 1,
    seen_test_ids: set[str] | None = None,
) -> tuple[list[TestCase], list[str]]:
    """Validate and convert all candidates for one requirement.

    Returns `(test_cases, issues)`. `test_cases` contains only fully valid
    records with traceability (source_context + generation metadata) already
    attached; every problem found is collected in `issues`.

    `auto_start` offsets auto-assigned ids (TC-###) so a multi-requirement
    request can number ids sequentially across suites. `seen_test_ids`
    carries ids already used in the same request, so duplicates are detected
    across the whole request, not just within one requirement.
    """
    issues: list[str] = []
    test_cases: list[TestCase] = []
    seen: set[str] = set() if seen_test_ids is None else seen_test_ids

    for index, candidate in enumerate(candidates, start=1):
        candidate_issues_list = candidate_issues(
            candidate,
            expected_requirement_id=expected_requirement_id,
            seen_test_ids=seen,
        )

        tid = (candidate.test_case_id or "").strip()
        if not tid:
            if auto_assign_ids:
                tid = f"TC-{auto_start + index - 1:03d}"
        if tid and _ID_RE.match(tid) and tid not in seen:
            seen.add(tid)

        if candidate_issues_list:
            issues.extend(candidate_issues_list)
            continue

        category = (candidate.category or "").strip().upper()
        priority = (candidate.priority or "").strip().upper()
        steps: list[TestStep] = []
        for num, step in enumerate(candidate.test_steps, start=1):
            if isinstance(step, TestStep):
                steps.append(TestStep(step_number=step.step_number, action=step.action.strip()))
            else:
                steps.append(TestStep(step_number=num, action=step.strip()))

        test_cases.append(
            TestCase(
                test_case_id=tid,
                requirement_id=expected_requirement_id,
                title=candidate.title.strip(),
                objective=candidate.objective.strip(),
                category=TestCategory(category),
                priority=TestPriority(priority),
                preconditions=[p.strip() for p in candidate.preconditions or [] if p.strip()],
                test_steps=steps,
                expected_result=candidate.expected_result.strip(),
                test_data=candidate.test_data,
                protocol=candidate.protocol,
                interface=candidate.interface,
                source_context=source_context,
                generation_metadata=metadata,
                assumptions=[a.strip() for a in candidate.assumptions or [] if a.strip()],
            )
        )
    return test_cases, issues


def raise_for_issues(issues: list[str]) -> None:
    """Raise a `TestValidationError` describing every collected problem."""
    if issues:
        raise TestValidationError(
            "Generated test cases failed validation:\n- " + "\n- ".join(issues)
        )