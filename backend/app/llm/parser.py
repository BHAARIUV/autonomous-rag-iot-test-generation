"""
Parsing of raw LLM responses into structured test-case candidates.

WHAT:
    `parse_test_cases(raw_text)` takes whatever an `LLMProvider` returned
    (real LLM or MOCK) and turns it into a list of loose
    `TestCaseCandidate` values. Fenced markdown JSON (```json ... ```) is
    stripped before parsing.

WHY:
    LLM output is untrusted: free-form prose around the JSON, or wrong
    JSON shapes, must fail loudly with a typed `ResponseParseError` rather
    than being silently guessed at. Semantic validation (categories,
    priorities, requirement match, uniqueness) happens in the validation
    layer after this structural parse.

HOW TO VERIFY:
    See tests/unit/test_llm_parser.py (valid, fenced, malformed, missing
    test_cases, single-case dict).
"""

from __future__ import annotations

import json
import re

from loguru import logger

from app.llm.errors import ResponseParseError
from app.llm.models import ResponsePayload, TestCaseCandidate

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)


def parse_test_cases(raw_text: str) -> list[TestCaseCandidate]:
    """Parse a provider response into structured candidates.

    Raises `ResponseParseError` when the response is not valid structured
    JSON or does not contain a non-empty `test_cases` array.
    """
    if not raw_text or not raw_text.strip():
        raise ResponseParseError("LLM returned an empty response")

    stripped = raw_text.strip()
    fenced = _FENCE.match(stripped)
    if fenced:
        stripped = fenced.group(1).strip()

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ResponseParseError(
            f"LLM response is not valid JSON: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ResponseParseError(
            "LLM response must be a JSON object with a 'test_cases' array; "
            f"got {type(data).__name__}"
        )

    try:
        payload = ResponsePayload.model_validate(data)
    except Exception as exc:
        raise ResponseParseError(f"LLM response failed schema validation: {exc}") from exc

    logger.debug(f"Parsed {len(payload.test_cases)} test case candidate(s) from LLM response")
    return payload.test_cases