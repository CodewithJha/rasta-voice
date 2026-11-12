"""Validation for typed LLM settings."""

import pytest

from rasta.extractors.http import close_shared_client, get_shared_client
from rasta.settings import (
    DEFAULT_EVENT_STORE_CAPACITY,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    SettingsError,
    clear_settings_cache,
    get_settings,
)


@pytest.fixture(autouse=True)
def _reset():
    close_shared_client()
    clear_settings_cache()
    yield
    close_shared_client()
    clear_settings_cache()


def test_defaults(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "GROQ_MODEL",
        "GEMINI_MODEL",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "EVENT_STORE_CAPACITY",
    ):
        monkeypatch.delenv(name, raising=False)
    clear_settings_cache()
    settings = get_settings()
    assert settings.llm_provider == "rules"
    assert settings.llm_timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS
    assert settings.llm_max_retries == 1
    assert settings.groq_model == DEFAULT_GROQ_MODEL
    assert settings.gemini_model == DEFAULT_GEMINI_MODEL
    assert settings.groq_api_key == ""
    assert settings.gemini_api_key == ""
    assert settings.event_store_capacity == DEFAULT_EVENT_STORE_CAPACITY


def test_invalid_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "-1")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="LLM_TIMEOUT_SECONDS"):
        get_settings()
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "fast")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="LLM_TIMEOUT_SECONDS"):
        get_settings()


def test_retries_cannot_exceed_one(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="LLM_MAX_RETRIES"):
        get_settings()
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    clear_settings_cache()
    assert get_settings().llm_max_retries == 0


def test_llm_model_overrides_only_the_active_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-flash-lite-latest")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    clear_settings_cache()
    settings = get_settings()
    assert settings.gemini_model == "gemini-flash-lite-latest"
    assert settings.groq_model == DEFAULT_GROQ_MODEL


def test_shared_client_uses_the_configured_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "2.5")
    clear_settings_cache()
    client = get_shared_client()
    assert client.timeout.read == 2.5
    # A later timeout change must not leave the old client in place.
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "3.5")
    clear_settings_cache()
    client = get_shared_client()
    assert client.timeout.read == 3.5


def test_non_finite_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch):
    for raw in ("nan", "NaN", "inf", "Infinity", "-inf", "-Infinity"):
        monkeypatch.setenv("LLM_TIMEOUT_SECONDS", raw)
        clear_settings_cache()
        with pytest.raises(SettingsError, match="LLM_TIMEOUT_SECONDS"):
            get_settings()


def test_non_finite_backoff_is_rejected(monkeypatch: pytest.MonkeyPatch):
    for raw in ("nan", "NaN", "inf", "Infinity", "-inf", "-Infinity"):
        monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", raw)
        clear_settings_cache()
        with pytest.raises(SettingsError, match="LLM_RETRY_BACKOFF_SECONDS"):
            get_settings()


def test_zero_timeout_is_rejected_but_zero_backoff_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "0")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="LLM_TIMEOUT_SECONDS"):
        get_settings()
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "0")
    clear_settings_cache()
    assert get_settings().llm_retry_backoff_seconds == 0.0


def test_negative_backoff_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_RETRY_BACKOFF_SECONDS", "-0.1")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="LLM_RETRY_BACKOFF_SECONDS"):
        get_settings()

