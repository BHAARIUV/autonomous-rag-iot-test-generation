"""
Phase 7 unit tests: LLM provider factory, no-API-key fallback, and the real
provider's failure behaviour (needs no network / no key).
"""

import sys

import pytest

from app.config import Settings
from app.llm.errors import LLMConfigurationError, LLMUnavailableError
from app.llm.providers import (
    MockLLMProvider,
    OpenAILLMProvider,
    create_llm_provider,
)


def test_default_settings_produce_mock_provider():
    cfg = Settings(_env_file=None)
    provider = create_llm_provider(settings_=cfg)
    assert isinstance(provider, MockLLMProvider)
    assert provider.generation_mode == "mock"


def test_openai_without_key_falls_back_to_mock():
    cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="")
    provider = create_llm_provider(settings_=cfg)
    assert isinstance(provider, MockLLMProvider)


def test_api_key_never_leaks_into_repr_or_generated_output():
    cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="sk-do-not-leak")
    provider = create_llm_provider(settings_=cfg)
    assert isinstance(provider, OpenAILLMProvider)
    assert provider.model == "gpt-4o-mini"
    assert "sk-do-not-leak" not in repr(provider)

    mock = MockLLMProvider(settings_=cfg)
    raw = mock.generate("system", "user")
    assert "sk-do-not-leak" not in raw
    assert "sk-do-not-leak" not in repr(mock)


def test_openai_with_key_configures_model_and_key():
    cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="sk-abc", LLM_MODEL="gpt-4o")
    provider = OpenAILLMProvider(settings_=cfg)
    assert provider.model == "gpt-4o"


def test_unimplemented_provider_with_key_raises_config_error():
    cfg = Settings(_env_file=None, LLM_PROVIDER="anthropic", LLM_API_KEY="sk-abc")
    with pytest.raises(LLMConfigurationError):
        create_llm_provider(settings_=cfg)


def test_unknown_provider_with_key_raises_config_error(monkeypatch):
    cfg = Settings(_env_file=None, LLM_PROVIDER="anthropic", LLM_API_KEY="sk-abc")
    monkeypatch.setattr(cfg, "llm_provider", "watson")  # bypass Literal for the factory's fallback branch
    with pytest.raises(LLMConfigurationError):
        create_llm_provider(settings_=cfg)


def test_openai_provider_without_key_raises_config_error():
    cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="")
    with pytest.raises(LLMConfigurationError):
        OpenAILLMProvider(settings_=cfg)


def test_mock_provider_never_needs_a_key():
    cfg = Settings(_env_file=None)
    provider = MockLLMProvider(settings_=cfg)
    assert provider.generate("sys", "user")  # deterministic plain JSON


def test_openai_generate_fails_lazily_when_package_missing(monkeypatch):
    cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="sk-abc")
    provider = OpenAILLMProvider(settings_=cfg)
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(LLMUnavailableError):
        provider.generate("system", "user")


def test_openai_generate_fails_lazily_when_call_fails(monkeypatch):
    cfg = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="sk-abc")
    provider = OpenAILLMProvider(settings_=cfg)

    class _Completions:
        def create(self, *args, **kwargs):
            raise RuntimeError("500 returned by provider")

    class _Chat:
        completions = _Completions()

    class _BoomClient:
        chat = _Chat()

    provider._client = lambda: _BoomClient()
    with pytest.raises(LLMUnavailableError):
        provider.generate("system", "user")