"""
Configurable embedding providers for the RAG subsystem.

WHAT:
    Two providers behind one `EmbeddingProvider` interface:
    - `HashingEmbeddingProvider` — deterministic, local, no network, no
      external API key. Default used for development and tests.
    - `OpenAIEmbeddingProvider` — a real embedding API, enabled by setting
      `EMBEDDING_PROVIDER=openai` plus `EMBEDDING_API_KEY`. The `openai`
      package is imported lazily so it is not required for tests.
    `create_embedding_provider()` builds the provider named by configuration.

WHY:
    The test suite must never depend on an external API, while production
    should be able to plug in a real provider through environment variables.
    Unknown / unavailable providers must fail with a clear, typed error
    instead of a bare traceback.

HOW:
    Embeddings are plain `list[float]` vectors. The local provider hashes
    word and character n-gram tokens (via sha256 — NOT Python's randomized
    builtin `hash()`) into a fixed-dimension, L2-normalized vector, so the
    same text always yields the same vector on every run and machine.

HOW TO VERIFY:
    See tests/unit/test_rag_embeddings.py.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from loguru import logger

from app.config import settings as _default_settings
from app.rag.errors import (
    EmbeddingConfigurationError,
    EmbeddingUnavailableError,
)

_WORD_RE = re.compile(r"[a-z0-9]+|[+\-]?\d+(?:\.\d+)?")

#: Generic English words that add no topical signal. Domain terms such as
#: "sensor", "temperature", "range", "mqtt" are intentionally NOT listed.
_STOPWORDS = frozenset(
    (
        "a", "an", "the", "and", "or", "but", "of", "to", "for", "in", "on",
        "at", "by", "from", "with", "is", "are", "was", "were", "be", "been",
        "that", "this", "these", "those", "it", "its", "as", "not", "so",
        "such", "than", "into", "over", "under", "after", "before", "during",
        "within", "without", "must", "shall", "should", "will", "would",
        "can", "could", "may", "might", "have", "has", "had", "do", "does",
        "did", "about", "then", "while", "when", "where", "how", "also",
        "very", "more", "most", "some", "any", "each", "every", "both",
        "other", "only", "just", "between", "out", "up", "down", "all",
        "like", "which", "who", "what", "why", "them", "they", "we", "you",
    )
)

#: Fixed default dimension for the OpenAI text-embedding-3-small family.
_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_OPENAI_DEFAULT_DIMENSION = 1536


def _stable_hash(token: str, dimension: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "big") % dimension


class EmbeddingProvider(ABC):
    """Produces vector embeddings for texts."""

    dimension: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts in one call (batched for API providers)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""

    def embed(self, texts: list[str]) -> list[list[float]]:  # convenience
        return self.embed_documents(texts)


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic, local, no-network embedding via token hashing.

    Suitable for development and tests: identical input always gives an
    identical vector, so indexing + retrieval are reproducible.
    """

    def __init__(self, dimension: int = 256):
        self.dimension = max(16, int(dimension))

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        vec = [0.0] * self.dimension
        tokens = [t for t in _WORD_RE.findall(lowered) if t not in _STOPWORDS]
        for token in tokens:
            numeric = token[0].isdigit() or (
                len(token) > 1 and token[0] in "+-"
            )
            weight = 2.0 if numeric else 1.0
            vec[_stable_hash(token, self.dimension)] += weight
            if len(token) > 1:  # in-token 2/3-grams add morphology signal
                for n in (2, 3):
                    for start in range(len(token) - n + 1):
                        vec[
                            _stable_hash(token[start : start + n], self.dimension)
                        ] += 0.5 * weight
        for pair in zip(tokens, tokens[1:]):
            vec[_stable_hash(f"{pair[0]}#{pair[1]}", self.dimension)] += 0.8
        norm = math.sqrt(sum(value * value for value in vec))
        if norm:
            vec = [value / norm for value in vec]
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Real embedding API provider (OpenAI), activated by configuration.

    The `openai` package is imported lazily: importing this module never
    requires it. If the package is missing or the API call fails, a typed
    `EmbeddingUnavailableError` is raised with a clear message.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        dimension: int = _OPENAI_DEFAULT_DIMENSION,
        settings_=None,
    ):
        cfg = settings_ if settings_ is not None else _default_settings
        self._api_key = api_key if api_key else cfg.embedding_api_key
        configured_model = model or cfg.embedding_model
        if configured_model in ("", "all-MiniLM-L6-v2"):
            configured_model = _OPENAI_DEFAULT_MODEL
        self._model = configured_model
        # OpenAI model dimensions differ from the local provider's; expose the
        # real dimension so callers that validate vector width can rely on it.
        self.dimension = cfg.embedding_dimension if cfg.embedding_dimension != 256 else dimension

    def _client(self):
        if not self._api_key:
            raise EmbeddingUnavailableError(
                "OpenAI embedding provider is configured but no API key is "
                "set (set EMBEDDING_API_KEY, or switch EMBEDDING_PROVIDER "
                "back to 'local')."
            )
        try:
            import openai  # installed separately; not required for tests
        except ImportError as exc:
            raise EmbeddingUnavailableError(
                "OpenAI embedding provider is configured but the 'openai' "
                "package is not installed."
            ) from exc
        return openai.OpenAI(api_key=self._api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client().embeddings.create(
                model=self._model, input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as exc:
            logger.warning(f"OpenAI embeddings failed: {exc}")
            raise EmbeddingUnavailableError(
                f"OpenAI embeddings call failed: {exc}"
            ) from exc

    def embed_query(self, text: str) -> list[float]:
        try:
            response = self._client().embeddings.create(
                model=self._model, input=[text]
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.warning(f"OpenAI embeddings failed: {exc}")
            raise EmbeddingUnavailableError(
                f"OpenAI embeddings call failed: {exc}"
            ) from exc


def create_embedding_provider(provider: str | None = None, settings_=None) -> EmbeddingProvider:
    """Build the embedding provider named by configuration.

    `provider` defaults to `settings.embedding_provider`. Known names:
    "local" / "hashing" (default, deterministic) and "openai" (real API).
    """
    cfg = settings_ if settings_ is not None else _default_settings
    name = (provider or cfg.embedding_provider or "local").strip().lower()
    if name in ("local", "hashing"):
        return HashingEmbeddingProvider(dimension=cfg.embedding_dimension)
    if name == "openai":
        return OpenAIEmbeddingProvider(settings_=cfg)
    raise EmbeddingConfigurationError(
        f"Unknown embedding provider '{name}'. Choose 'local' or 'openai'."
    )