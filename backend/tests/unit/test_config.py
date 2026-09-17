"""
Phase 1 unit test: confirms Settings loads with sane defaults even when
no .env file / API keys are present (mock mode), which is the state a
fresh clone of this repo should always start in.
"""

from app.config import Settings


def test_settings_load_with_defaults():
    s = Settings(_env_file=None)  # ignore any local .env for this test
    assert s.app_env in {"development", "testing", "production"}
    assert s.mqtt_broker_port == 1883
    assert s.max_refinement_iterations == 3
    assert s.target_requirement_coverage == 90.0
    assert s.target_fault_detection == 90.0


def test_mock_llm_is_default_when_no_api_key():
    s = Settings(_env_file=None, LLM_API_KEY="")
    assert s.is_mock_llm is True


def test_real_llm_mode_when_key_and_provider_set():
    s = Settings(_env_file=None, LLM_PROVIDER="openai", LLM_API_KEY="sk-test")
    assert s.is_mock_llm is False
