"""
Typed exceptions for the Phase 7 LLM test-generation subsystem.

WHY:
    Callers (the service layer, later phases, tests) need to distinguish
    why generation failed instead of catching a bare Exception:
    configuration problems, unavailable provider, unparseable LLM output,
    or invalid generated test content. Everything shares `GenerationError`
    as the base so one except clause can catch the whole subsystem.

HOW:
    - `LLMConfigurationError`  — provider misconfigured (e.g. unknown
      provider name requested with a key configured).
    - `LLMUnavailableError`    — provider selected but unusable right now
      (package missing, API call failed, network down). NEVER wraps or
      logs an API key.
    - `ResponseParseError`     — the LLM returned content that is not
      parseable as the expected structured JSON.
    - `TestValidationError`    — the LLM produced structurally valid JSON
      whose test cases fail validation (missing fields, unknown category,
      duplicate ids, requirement mismatch, empty steps...).
    - `EmptyRequirementError`  — generation called with a blank/missing
      requirement.

HOW TO VERIFY:
    See tests/unit/test_llm_service.py (provider failure, malformed
    response, invalid content) and tests/unit/test_llm_validation.py.
"""

from __future__ import annotations


class GenerationError(Exception):
    """Base class for every error raised by the LLM generation subsystem."""


class LLMConfigurationError(GenerationError):
    """The LLM provider is invalid / misconfigured (unknown provider...)."""


class LLMUnavailableError(GenerationError):
    """A real LLM provider was requested but cannot be called right now
    (package missing, no API key, or the remote API failed)."""


class ResponseParseError(GenerationError):
    """The LLM response could not be interpreted as the required structured
    JSON payload (not JSON, malformed JSON, or missing the test_cases key)."""


class TestValidationError(GenerationError):
    """Generated test cases failed validation and were rejected —
    malformed content is never silently repaired into valid tests."""


class EmptyRequirementError(GenerationError):
    """Generation was requested for a blank / missing requirement."""