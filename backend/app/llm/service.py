"""
Phase 7 generation service: requirements + RAG context -> LLM -> validated
structured test cases.

WHAT:
    `GenerationService` wraps the whole Phase 7 pipeline for one or many
    requirements:

        requirement
            -> RAG retrieval (existing Phase 6 service, when provided)
            -> prompt construction (requirement + retrieved knowledge)
            -> LLM provider (MOCK by default; real provider when configured)
            -> structured JSON parsing
            -> validation (typed errors, no silent repair)
            -> `GeneratedTestSuite` / `list[GeneratedTestSuite]`

    Every generated test case carries:
        requirement_id (traceability to the source requirement),
        source_context (which RAG chunks were used),
        generation_metadata (provider, mode, prompt version, timestamp,
        retrieved chunk ids).

WHY:
    Later phases (validation, execution, coverage) consume structured test
    cases. This service is the only public entry point they should use.

HOW:
    - `generate_for_requirement(requirement)`  — one requirement -> suite.
    - `generate_for_requirements(requirements)` — many requirements -> list
      of suites, with test_case ids unique across the whole request.
    - `_retrieve(...)` reuses `RagService.retrieve_for_requirement` when a
      RAG service is provided; with no RAG service the generator runs on the
      requirement alone (source_context is then absent).
    - Provider/api behaviour follows the existing `Settings.is_mock_llm`
      convention: no key => MOCK mode, never an unusable app.

HOW TO VERIFY:
    See tests/unit/test_llm_service.py and
    tests/integration/test_llm_generation.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from app.llm.errors import EmptyRequirementError
from app.llm.models import (
    GeneratedTestSuite,
    GenerationMetadata,
    SourceContext,
    SourceContextItem,
)
from app.llm.parser import parse_test_cases
from app.llm.prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt
from app.llm.providers import LLMProvider, create_llm_provider
from app.llm.validation import raise_for_issues, validate_candidates
from app.rag.service import requirement_query_text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GenerationService:
    """Generates validated, structured test cases for requirements."""

    def __init__(
        self,
        *,
        settings_=None,
        provider: LLMProvider | None = None,
        rag_service=None,
        top_k: int | None = None,
    ):
        from app.config import settings as _singleton

        self._settings = settings_ if settings_ is not None else _singleton
        self._provider = provider if provider is not None else create_llm_provider(
            settings_=self._settings
        )
        self._rag_service = rag_service
        self._top_k = top_k if top_k is not None else self._settings.rag_top_k

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    # ------------------------------------------------------------- public API

    def generate_for_requirement(
        self,
        requirement,
        *,
        top_k: int | None = None,
    ) -> GeneratedTestSuite:
        """Generate a test suite for a single requirement."""
        return self.generate_for_requirements([requirement], top_k=top_k)[0]

    def generate_for_requirements(
        self,
        requirements,
        *,
        top_k: int | None = None,
    ) -> list[GeneratedTestSuite]:
        """Generate test suites for several requirements.

        `test_case_id` values are unique across the whole request.
        """
        k = self._top_k if top_k is None else int(top_k)
        suites: list[GeneratedTestSuite] = []
        seen_test_ids: set[str] = set()
        auto_start = 1

        for requirement in requirements:
            rid, description = self._validate_requirement(requirement)

            retrieval = self._retrieve(requirement, k)
            source_context = self._source_context(requirement, retrieval)

            system_prompt = build_system_prompt()
            user_prompt = build_user_prompt(requirement, retrieval)
            raw = self._provider.generate(system_prompt, user_prompt)

            candidates = parse_test_cases(raw)
            metadata = GenerationMetadata(
                provider=self._provider.name,
                model=self._provider.model,
                generation_mode=self._provider.generation_mode,
                prompt_version=PROMPT_VERSION,
                timestamp=_now_iso(),
                retrieved_chunk_ids=[r.chunk_id for r in retrieval],
            )

            test_cases, issues = validate_candidates(
                candidates,
                expected_requirement_id=rid,
                metadata=metadata,
                source_context=source_context,
                auto_start=auto_start,
                seen_test_ids=seen_test_ids,
            )
            raise_for_issues(issues)

            auto_start += len(test_cases)
            suites.append(
                GeneratedTestSuite(
                    requirement_id=rid,
                    test_cases=test_cases,
                    generation_metadata=metadata,
                )
            )
            logger.info(
                f"Generated {len(test_cases)} validated test case(s) for "
                f"{rid} ({metadata.generation_mode} mode, {metadata.provider})"
            )
        return suites

    # --------------------------------------------------------------- internals

    @staticmethod
    def _validate_requirement(requirement) -> tuple[str, str]:
        if not hasattr(requirement, "requirement_id") or not hasattr(requirement, "description"):
            raise EmptyRequirementError(
                "generate_for_requirement expects a Phase 5 Requirement "
                "object with requirement_id and description."
            )
        rid = (requirement.requirement_id or "").strip()
        description = (requirement.description or "").strip()
        if not rid:
            raise EmptyRequirementError("requirement_id is missing from the requirement")
        if not description:
            raise EmptyRequirementError(
                f"requirement {rid} has an empty description — nothing to generate tests for"
            )
        return rid, description

    def _retrieve(self, requirement, top_k: int) -> list:
        """Retrieve RAG context via the existing Phase 6 service (reused)."""
        if self._rag_service is None:
            logger.debug(
                "No RAG service configured; generating tests from the requirement only"
            )
            return []
        results = self._rag_service.retrieve_for_requirement(requirement, top_k=top_k)
        logger.debug(f"Retrieved {len(results)} RAG chunk(s) for test generation")
        return results

    @staticmethod
    def _source_context(requirement, retrieval: list) -> SourceContext | None:
        if not retrieval:
            return None
        return SourceContext(
            retrieval_query=requirement_query_text(requirement),
            chunks=[
                SourceContextItem(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    source=r.source,
                    title=r.title,
                    topic=r.topic,
                    relevance=r.relevance,
                )
                for r in retrieval
            ],
        )


# ---------------------------------------------------------------------------
# Module-level convenience API operating on the default configured setup
# ---------------------------------------------------------------------------

_DEFAULT_SERVICE: GenerationService | None = None


def get_default_service() -> GenerationService:
    """Lazily-built shared `GenerationService` using project configuration."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        from app.rag.service import get_default_service as _get_default_rag

        _DEFAULT_SERVICE = GenerationService(rag_service=_get_default_rag())
    return _DEFAULT_SERVICE


def reset_default_service() -> None:
    """Drop the cached default service (used by tests to avoid stale state)."""
    global _DEFAULT_SERVICE
    _DEFAULT_SERVICE = None


def generate_for_requirement(
    requirement, *, top_k: int | None = None
) -> GeneratedTestSuite:
    """Generate a validated test suite for one requirement via the default setup."""
    return get_default_service().generate_for_requirement(requirement, top_k=top_k)


def generate_for_requirements(
    requirements, *, top_k: int | None = None
) -> list[GeneratedTestSuite]:
    """Generate validated test suites for several requirements."""
    return get_default_service().generate_for_requirements(requirements, top_k=top_k)