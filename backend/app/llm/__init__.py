"""
Phase 7 — LLM-Based IoT Test Case Generation.

WHAT:
    Generates structured, validated IoT test cases from Phase 5 extracted
    requirements plus Phase 6 retrieved RAG knowledge:

        Requirement -> RAG retrieval (Phase 6 service)
                     -> prompt construction
                     -> LLM provider (MOCK by default; openai when configured)
                     -> structured JSON parsing
                     -> validation
                     -> GeneratedTestSuite / list[GeneratedTestSuite]

    Every generated test case preserves full traceability: requirement_id ->
    retrieved RAG chunk ids -> test case -> generation_metadata. Generated
    test cases are TEST SPECIFICATIONS ONLY — nothing is executed, and LLM /
    RAG / requirement content is never treated as executable code.

WHY:
    This is Phase 7 of the framework. Test execution, fault injection changes,
    coverage analysis and refinement belong to later phases and are NOT part
    of this phase.

HOW:
    - MOCK mode is the default (existing `Settings.is_mock_llm` convention):
      no API key needed, deterministic and offline so the full test suite runs
      without external services.
    - Set `LLM_PROVIDER=openai` + `LLM_API_KEY` (via .env / env vars) for a
      real provider; API keys are never logged or stored.
    - Malformed LLM output fails safely with typed errors; invalid content is
      rejected, never silently repaired.

HOW TO VERIFY:
    - `venv\\Scripts\\python.exe -m pytest tests/unit/test_llm_*.py -q`
    - `venv\\Scripts\\python.exe -m pytest tests/integration/test_llm_generation.py -q`
"""

from app.llm.errors import (
    EmptyRequirementError,
    GenerationError,
    LLMConfigurationError,
    LLMUnavailableError,
    ResponseParseError,
    TestValidationError,
)
from app.llm.models import (
    GeneratedTestSuite,
    GenerationMetadata,
    SourceContext,
    SourceContextItem,
    TRACEABILITY_FIELDS,
    TestCase,
    TestCaseCandidate,
    TestCategory,
    TestData,
    TestPriority,
    TestStep,
)
from app.llm.parser import parse_test_cases
from app.llm.prompts import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt,
)
from app.llm.providers import (
    LLMProvider,
    MockLLMProvider,
    OpenAILLMProvider,
    create_llm_provider,
)
from app.llm.service import (
    GenerationService,
    generate_for_requirement,
    generate_for_requirements,
    get_default_service,
    reset_default_service,
)
from app.llm.validation import (
    candidate_issues,
    raise_for_issues,
    validate_candidates,
)

__all__ = [
    # errors
    "GenerationError",
    "LLMConfigurationError",
    "LLMUnavailableError",
    "ResponseParseError",
    "TestValidationError",
    "EmptyRequirementError",
    # models
    "TestCase",
    "TestCaseCandidate",
    "GeneratedTestSuite",
    "GenerationMetadata",
    "SourceContext",
    "SourceContextItem",
    "TestCategory",
    "TestPriority",
    "TestStep",
    "TestData",
    "TRACEABILITY_FIELDS",
    # providers
    "LLMProvider",
    "MockLLMProvider",
    "OpenAILLMProvider",
    "create_llm_provider",
    # prompts
    "PROMPT_VERSION",
    "build_system_prompt",
    "build_user_prompt",
    # parsing / validation
    "parse_test_cases",
    "candidate_issues",
    "validate_candidates",
    "raise_for_issues",
    # service
    "GenerationService",
    "generate_for_requirement",
    "generate_for_requirements",
    "get_default_service",
    "reset_default_service",
]