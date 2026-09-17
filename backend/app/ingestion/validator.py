"""
WHAT:
    Validates extracted `Requirement`s for structural correctness and
    source-traceability completeness before they leave the ingestion
    pipeline.

WHY:
    Later phases (RAG retrieval, LLM test generation, coverage analysis)
    depend on requirements being complete and well-formed. Validation
    here catches defects early with actionable messages instead of
    letting a malformed requirement silently propagate.

HOW:
    - `validate_requirement` checks a single requirement.
    - `validate_requirements` checks a whole list, including duplicate /
      out-of-sequence ids.
    - Returns a list of human-readable issue strings (empty = valid);
      it never mutates and never raises — callers decide how to react.

HOW TO VERIFY:
    See tests/unit/test_spec_validator.py.
"""

from __future__ import annotations

import re

from app.ingestion.models import (
    CONSTRAINT_KINDS,
    Requirement,
    RequirementCategory,
)

_ID_RE = re.compile(r"^REQ-\d{3}$")
_CATEGORY_VALUES = {c.value for c in RequirementCategory}


def validate_requirement(requirement: Requirement) -> list[str]:
    """Return a list of issues for one requirement ([] when valid)."""
    issues: list[str] = []
    req_id = requirement.requirement_id

    if not _ID_RE.match(req_id):
        issues.append(
            f"requirement_id '{req_id}' does not match the expected "
            "'REQ-###' format."
        )
    if not requirement.description.strip():
        issues.append(f"{req_id}: description is empty.")
    if requirement.category is None:
        issues.append(f"{req_id}: category is missing.")
    elif requirement.category.value not in _CATEGORY_VALUES:
        issues.append(f"{req_id}: category '{requirement.category}' is unknown.")
    if not requirement.source.strip():
        issues.append(f"{req_id}: source is empty (traceability missing).")
    if not requirement.source_reference.strip():
        issues.append(
            f"{req_id}: source_reference is empty (traceability missing)."
        )
    for constraint in requirement.constraints:
        if not constraint.value.strip():
            issues.append(f"{req_id}: constraint with empty value.")
        if constraint.kind not in CONSTRAINT_KINDS:
            issues.append(
                f"{req_id}: unsupported constraint kind '{constraint.kind}'."
            )
    return issues


def validate_requirements(requirements: list[Requirement]) -> list[str]:
    """Validate a whole requirement list, including id sequencing."""
    issues: list[str] = []
    seen: set[str] = set()

    for index, requirement in enumerate(requirements, start=1):
        issues.extend(validate_requirement(requirement))
        req_id = requirement.requirement_id
        expected = f"REQ-{index:03d}"
        if req_id != expected:
            issues.append(
                f"expectation mismatch: requirements must be sequentially "
                f"numbered REQ-001..; found '{req_id}' at position {index} "
                f"(expected '{expected}')."
            )
        if req_id in seen:
            issues.append(f"duplicate requirement id '{req_id}'.")
        seen.add(req_id)

    return issues