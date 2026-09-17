"""
Structured data model for the Phase 7 LLM test-generation subsystem.

WHY:
    Generated test cases are the main deliverable of this phase and the
    input to later phases (validation, execution, coverage). They must be
    a single, typed, JSON-serializable contract that preserves full
    traceability: requirement_id -> retrieved RAG chunks -> test case ->
    generation_metadata.

WHAT:
    - `TestCategory` / `TestPriority`  — canonical test design dimensions.
    - `TestStep`                        — one ordered step of a test.
    - `TestData`                        — typed inputs/expected values.
    - `SourceContextItem` / `SourceContext` — which RAG knowledge was used.
    - `GenerationMetadata`              — provider, mode, prompt version,
      timestamp, retrieved chunk ids. NEVER stores API keys.
    - `TestCase`                        — one generated, validated test.
    - `GeneratedTestSuite`              — all tests generated for one
      requirement, plus the run's generation metadata.
    - `ResponsePayload` / `TestCaseCandidate` — the wire format the LLM
      returns; loose, then tightened by the validation layer.

HOW:
    Frozen pydantic models match `app/ingestion/models.py` and
    `app/rag/models.py`.

HOW TO VERIFY:
    See tests/unit/test_llm_models.py.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TRACEABILITY_FIELDS = (
    "requirement_id",
    "test_case_id",
    "source_context",
    "generation_metadata",
)

_PROTOCOL_CHOICES = frozenset({"MQTT", "SENSOR", "CLI"})


class TestCategory(str, Enum):
    """Supported generated-test categories."""

    POSITIVE = "POSITIVE"
    BOUNDARY = "BOUNDARY"
    NEGATIVE = "NEGATIVE"
    EQUIVALENCE = "EQUIVALENCE"
    TIMING = "TIMING"
    COMMUNICATION = "COMMUNICATION"
    RELIABILITY = "RELIABILITY"
    DATA_VALIDATION = "DATA_VALIDATION"


class TestPriority(str, Enum):
    """Priority of a generated test. Values align with RequirementSeverity
    so the project speaks one severity language (LOW..CRITICAL)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TestStep(BaseModel):
    """One ordered step within a generated test."""

    model_config = {"frozen": True}

    step_number: int = Field(ge=1, description="1-based position in the test")
    action: str = Field(min_length=1, description="What to do in this step")

    @field_validator("action")
    @classmethod
    def _action_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("test step action must not be blank")
        return stripped


class TestData(BaseModel):
    """Typed inputs and expected values of a test (unstructured strings or
    structured key/value pairs, depending on what the test needs)."""

    model_config = {"frozen": True}

    description: str | None = Field(
        default=None, description="Human note on the data set, if any"
    )
    inputs: dict[str, str] = Field(
        default_factory=dict, description="Inputs, e.g. {'temperature': '-40'}"
    )
    expected: dict[str, str] = Field(
        default_factory=dict, description="Expected values, e.g. {'status': 'VALID'}"
    )


class SourceContextItem(BaseModel):
    """Compact reference to one retrieved RAG knowledge chunk."""

    model_config = {"frozen": True}

    chunk_id: str
    document_id: str
    source: str
    title: str
    topic: str
    relevance: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Retrieval relevance score (1 - distance)"
    )


class SourceContext(BaseModel):
    """The RAG knowledge a generated test was based on."""

    model_config = {"frozen": True}

    retrieval_query: str = Field(
        default="", description="Query string sent to the retriever"
    )
    chunks: list[SourceContextItem] = Field(
        default_factory=list, description="Ordered retrieved chunks (most relevant first)"
    )


class GenerationMetadata(BaseModel):
    """Provenance of one generation run. Never stores API keys."""

    model_config = {"frozen": True}

    provider: str = Field(description="Provider name, e.g. 'mock' or 'openai'")
    model: str = Field(description="Model identifier used by the provider")
    generation_mode: Literal["mock", "llm"] = Field(
        description="'mock' = deterministic local generation; 'llm' = real LLM call"
    )
    prompt_version: str = Field(description="Prompt template version identifier")
    timestamp: str = Field(description="ISO 8601 UTC timestamp of the run")
    retrieved_chunk_ids: list[str] = Field(
        default_factory=list, description="Chunk ids used as RAG context (traceability)"
    )


class TestCase(BaseModel):
    """One validated, traceable generated test case."""

    model_config = {"frozen": True}

    test_case_id: str = Field(description="Unique id within a generation request, e.g. TC-001")
    requirement_id: str = Field(description="The requirement this test traces back to")
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1, description="What the test verifies")
    category: TestCategory
    priority: TestPriority
    preconditions: list[str] = Field(
        default_factory=list, description="State / preconditions required before the test"
    )
    test_steps: list[TestStep] = Field(
        min_length=1, description="Ordered steps (at least one)"
    )
    expected_result: str = Field(min_length=1)
    test_data: TestData | None = Field(
        default=None, description="Structured inputs / expected values"
    )
    protocol: str | None = Field(default=None, description="Protocol under test, e.g. MQTT")
    interface: str | None = Field(default=None, description="Interface, e.g. topic name")
    source_context: SourceContext | None = Field(
        default=None, description="RAG knowledge this test was based on"
    )
    generation_metadata: GenerationMetadata
    assumptions: list[str] = Field(
        default_factory=list, description="Assumptions the test makes (when unavoidable)"
    )

    @field_validator("protocol")
    @classmethod
    def _protocol_known(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v.upper() not in _PROTOCOL_CHOICES:
            raise ValueError(
                f"unknown protocol '{v}'; expected one of {sorted(_PROTOCOL_CHOICES)}"
            )
        return v.upper()


class GeneratedTestSuite(BaseModel):
    """All test cases generated for one requirement, plus run metadata."""

    model_config = {"frozen": True}

    requirement_id: str
    test_cases: list[TestCase] = Field(min_length=1)
    generation_metadata: GenerationMetadata


# ---------------------------------------------------------------------------
# Wire format returned by the LLM / mock provider (loose, validated later)
# ---------------------------------------------------------------------------


class TestCaseCandidate(BaseModel):
    """The loose shape an LLM response entry arrives in. The validation
    layer converts candidates into strict `TestCase` values, or rejects."""

    test_case_id: str = ""
    requirement_id: str = ""
    title: str = ""
    objective: str = ""
    category: str = ""
    priority: str = ""
    preconditions: list[str] = Field(default_factory=list)
    test_steps: list[TestStep | str] = Field(default_factory=list)
    expected_result: str = ""
    test_data: dict | None = None
    protocol: str | None = None
    interface: str | None = None
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("test_data")
    @classmethod
    def _test_data_shape(cls, v):
        if v is None:
            return v
        if not isinstance(v, dict):
            raise ValueError("test_data must be a JSON object")
        keys = set(v)
        unknown = keys - {"description", "inputs", "expected"}
        if unknown:
            raise ValueError(
                f"test_data contains unknown keys: {sorted(unknown)}. "
                "Allowed: description, inputs, expected."
            )
        return v


class ResponsePayload(BaseModel):
    """Top-level structured response expected from the LLM."""

    model_config = {"extra": "ignore"}

    test_cases: list[TestCaseCandidate] = Field(default_factory=list)
    summary: str | None = Field(
        default=None, description="Optional free-form summary (ignored for tests)"
    )

    @model_validator(mode="after")
    def _require_some_tests(self) -> "ResponsePayload":
        if not self.test_cases:
            raise ValueError("response contains no test_cases")
        return self