"""Validation for typed LLM settings."""

import pytest

from rasta.extractors.http import close_shared_client, get_shared_client
from rasta.settings import (
    DEFAULT_CORS_ALLOW_ORIGINS,
    DEFAULT_EVENT_STORE_CAPACITY,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_MAX_STREAMS,
    DEFAULT_RASTA_DB_PATH,
    DEFAULT_STREAM_FRAME_BYTES,
    DEFAULT_STREAM_IDLE_SECONDS,
    DEFAULT_STREAM_SAMPLE_RATE,
    DEFAULT_STREAM_SESSION_SECONDS,
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
        "RASTA_DB_PATH",
        "RASTA_MAX_STREAMS",
        "RASTA_STREAM_SESSION_SECONDS",
        "RASTA_STREAM_IDLE_SECONDS",
        "RASTA_STREAM_HEARTBEAT_SECONDS",
        "RASTA_STREAM_DRAIN_SECONDS",
        "RASTA_STREAM_FRAME_BYTES",
        "RASTA_STREAM_QUEUE_MAX",
        "RASTA_STREAM_SAMPLE_RATE",
        "CORS_ALLOW_ORIGINS",
    ):
        monkeypatch.delenv(name, raising=False)
    clear_settings_cache()
    settings = get_settings()
    assert settings.llm_provider == "rules"
    assert settings.llm_timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS
    assert settings.llm_max_retries == 1
    assert settings.connect_timeout_seconds == 5.0
    assert settings.stt_read_timeout_seconds == 15.0
    assert settings.tts_read_timeout_seconds == 20.0
    assert settings.ingest_deadline_seconds == 25.0
    assert settings.max_inflight == 4
    assert settings.upstream_max_retries == 2
    assert settings.breaker_failure_threshold == 5
    assert settings.groq_model == DEFAULT_GROQ_MODEL
    assert settings.gemini_model == DEFAULT_GEMINI_MODEL
    assert settings.groq_api_key == ""
    assert settings.gemini_api_key == ""
    assert settings.event_store_capacity == DEFAULT_EVENT_STORE_CAPACITY
    assert settings.db_path == DEFAULT_RASTA_DB_PATH
    assert settings.max_streams == DEFAULT_MAX_STREAMS
    assert settings.stream_session_seconds == DEFAULT_STREAM_SESSION_SECONDS
    assert settings.stream_idle_seconds == DEFAULT_STREAM_IDLE_SECONDS
    assert settings.stream_frame_bytes == DEFAULT_STREAM_FRAME_BYTES
    assert settings.stream_sample_rate == DEFAULT_STREAM_SAMPLE_RATE
    assert settings.cors_allow_origins == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    # The constant is the env default string; the field is the parsed tuple.
    assert ",".join(settings.cors_allow_origins) == DEFAULT_CORS_ALLOW_ORIGINS


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


def test_stream_limits_are_validated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_MAX_STREAMS", "0")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="RASTA_MAX_STREAMS"):
        get_settings()
    monkeypatch.setenv("RASTA_MAX_STREAMS", "3")
    clear_settings_cache()
    assert get_settings().max_streams == 3


def test_odd_frame_bytes_are_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_STREAM_FRAME_BYTES", "1023")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="even"):
        get_settings()


def test_cors_wildcard_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://ok.example,*")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="must not contain"):
        get_settings()


def test_empty_cors_allow_list(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "")
    clear_settings_cache()
    assert get_settings().cors_allow_origins == ()


def test_short_idle_is_clamped_for_the_prisma_header(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "0.2")
    clear_settings_cache()
    settings = get_settings()
    assert settings.stream_idle_seconds == 0.2
    assert settings.prisma_idle_timeout_sec() == 5


def test_unknown_rasta_env_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_ENV", "staging")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="RASTA_ENV"):
        get_settings()
    clear_settings_cache()


def test_development_budget_default_is_generous(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RASTA_DEMO_SPEECH_BUDGET", raising=False)
    monkeypatch.delenv("RASTA_PER_IP_REQUESTS_PER_MINUTE", raising=False)
    monkeypatch.delenv("RASTA_MAX_CONCURRENT_SPEECH", raising=False)
    monkeypatch.setenv("RASTA_ENV", "development")
    clear_settings_cache()
    settings = get_settings()
    assert settings.demo_speech_budget == 10_000
    assert settings.per_ip_requests_per_minute == 10_000
    assert settings.max_concurrent_speech == 32
    clear_settings_cache()


def test_db_path_default_and_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RASTA_DB_PATH", raising=False)
    clear_settings_cache()
    assert get_settings().db_path == DEFAULT_RASTA_DB_PATH
    monkeypatch.setenv("RASTA_DB_PATH", "/app/data/rasta-events.sqlite")
    clear_settings_cache()
    assert get_settings().db_path == "/app/data/rasta-events.sqlite"


@pytest.mark.parametrize("raw", [":memory:", "file:desk?mode=memory"])
def test_db_path_rejects_in_memory(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv("RASTA_DB_PATH", raw)
    clear_settings_cache()
    with pytest.raises(SettingsError, match="RASTA_DB_PATH"):
        get_settings()
