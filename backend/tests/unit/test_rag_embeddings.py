"""
Phase 6 unit tests: embedding providers — the deterministic local provider and
the configurable (gracefully-failing) OpenAI provider.
"""

import math
import sys

import pytest

from app.config import Settings
from app.rag.embeddings import (
    HashingEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)
from app.rag.errors import (
    EmbeddingConfigurationError,
    EmbeddingUnavailableError,
)


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def test_local_provider_dimension_from_config():
    provider = HashingEmbeddingProvider()
    assert provider.dimension > 0
    vec = provider.embed_query("temperature range")
    assert len(vec) == provider.dimension


def test_local_provider_deterministic():
    provider = HashingEmbeddingProvider(dimension=256)
    assert provider.embed_query("MQTT QoS 1 reconnect") == provider.embed_query(
        "MQTT QoS 1 reconnect"
    )
    assert provider.embed_documents(["a"]) == provider.embed_documents(["a"])


def test_local_provider_vectors_normalized():
    provider = HashingEmbeddingProvider(dimension=256)
    vec = provider.embed_query("boundary value analysis range test")
    norm = math.sqrt(sum(x * x for x in vec))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_local_provider_similar_texts_rank_above_dissimilar():
    provider = HashingEmbeddingProvider(dimension=256)
    a = provider.embed_query("temperature sensor range measurement")
    b = provider.embed_query("temperature sensor range measurement accuracy")
    c = provider.embed_query("mqtt message publish subscribe broker topic")
    assert _cosine(a, b) > _cosine(a, c)


def test_local_provider_empty_text_zero_vector():
    provider = HashingEmbeddingProvider(dimension=128)
    assert provider.embed_query("") == [0.0] * 128


def test_local_provider_batches_match_individual():
    provider = HashingEmbeddingProvider(dimension=256)
    texts = ["temperature range", "mqtt protocol"]
    batch = provider.embed_documents(texts)
    assert len(batch) == 2
    assert batch[0] == provider.embed_query(texts[0])
    assert batch[1] == provider.embed_query(texts[1])


def test_create_embedding_provider_local_default():
    provider = create_embedding_provider("local")
    assert isinstance(provider, HashingEmbeddingProvider)
    assert isinstance(create_embedding_provider("hashing"), HashingEmbeddingProvider)


def test_create_embedding_provider_from_settings():
    cfg = Settings(_env_file=None, EMBEDDING_PROVIDER="local")
    assert isinstance(create_embedding_provider(settings_=cfg), HashingEmbeddingProvider)


def test_create_embedding_provider_unknown_raises():
    with pytest.raises(EmbeddingConfigurationError):
        create_embedding_provider("pinecone")


def test_openai_without_key_fails_gracefully():
    cfg = Settings(_env_file=None, EMBEDDING_PROVIDER="openai", EMBEDDING_API_KEY="")
    provider = OpenAIEmbeddingProvider(settings_=cfg)
    with pytest.raises(EmbeddingUnavailableError) as excinfo:
        provider.embed_documents(["hello"])
    assert "API key" in str(excinfo.value)


def test_openai_without_package_fails_gracefully(monkeypatch):
    cfg = Settings(_env_file=None, EMBEDDING_PROVIDER="openai", EMBEDDING_API_KEY="sk-x")
    provider = OpenAIEmbeddingProvider(settings_=cfg)
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(EmbeddingUnavailableError) as excinfo:
        provider.embed_query("hello")
    assert "not installed" in str(excinfo.value)


def test_openai_provider_model_fallback():
    cfg = Settings(_env_file=None, EMBEDDING_PROVIDER="openai", EMBEDDING_MODEL="")
    provider = OpenAIEmbeddingProvider(settings_=cfg)
    assert provider._model == "text-embedding-3-small"


def test_openai_default_model_passthrough():
    cfg = Settings(
        _env_file=None,
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_MODEL="text-embedding-3-large",
    )
    provider = OpenAIEmbeddingProvider(settings_=cfg)
    assert provider._model == "text-embedding-3-large"