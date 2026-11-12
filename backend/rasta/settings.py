"""Typed process settings loaded from the environment.

Issue 02 owns the LLM keys, model ids, timeout, and retry cap. Issue 04
owns the in-memory event-store capacity. Call ``get_settings()`` rather
than ``os.environ`` so a typo, a negative timeout, or a non-positive
capacity fails in one place. ``clear_settings_cache`` exists so tests
can change the env without restarting the process.

Issue 29 will share the HTTP client; the timeout here is the value that
client must keep using for LLM calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from os import environ

# Env names. Importers should use these instead of string literals.
ENV_LLM_PROVIDER = "LLM_PROVIDER"
ENV_LLM_MODEL = "LLM_MODEL"
ENV_LLM_TIMEOUT_SECONDS = "LLM_TIMEOUT_SECONDS"
ENV_LLM_MAX_RETRIES = "LLM_MAX_RETRIES"
ENV_LLM_RETRY_BACKOFF_SECONDS = "LLM_RETRY_BACKOFF_SECONDS"
ENV_GROQ_API_KEY = "GROQ_API_KEY"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
ENV_GROQ_MODEL = "GROQ_MODEL"
ENV_GEMINI_MODEL = "GEMINI_MODEL"
ENV_GROQ_BASE_URL = "GROQ_BASE_URL"
ENV_GEMINI_BASE_URL = "GEMINI_BASE_URL"
ENV_EVENT_STORE_CAPACITY = "EVENT_STORE_CAPACITY"

# Checked 12 Nov 2026 against Groq deprecations: llama-3.1-8b-instant was
# withdrawn for free and developer tiers on 16 Aug 2026. openai/gpt-oss-20b
# is the documented free-tier replacement.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"

# Checked 12 Nov 2026 against Google AI Studio model docs: new work should
# use gemini-3.5-flash-lite (or 3.8 Flash). gemini-2.0-flash is shut down;
# gemini-2.5-flash is limited to existing users.
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_LLM_PROVIDER = "rules"
DEFAULT_LLM_TIMEOUT_SECONDS = 4.0
# One retry means two attempts in total. The issue cap is "do not retry
# more than once".
DEFAULT_LLM_MAX_RETRIES = 1
DEFAULT_LLM_RETRY_BACKOFF_SECONDS = 0.25

# The issue 04 cap is 200. EventStore receives the validated value; it
# does not read the environment itself.
DEFAULT_EVENT_STORE_CAPACITY = 200
# Hard ceiling so a typo cannot allocate unbounded memory in one process.
MAX_EVENT_STORE_CAPACITY = 10_000

ALLOWED_PROVIDERS = frozenset({"rules", "groq", "gemini"})
MAX_ALLOWED_RETRIES = 1


class SettingsError(ValueError):
    """Raised when an environment value cannot be used as settings."""


def _raw(name: str, default: str = "") -> str:
    return environ.get(name, default).strip()


def _positive_float(name: str, default: float) -> float:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a positive number, got {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise SettingsError(f"{name} must be a positive finite number, got {raw!r}")
    return value


def _non_negative_float(name: str, default: float) -> float:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a number >= 0, got {raw!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise SettingsError(f"{name} must be a finite number >= 0, got {raw!r}")
    return value


def _retry_count(name: str, default: int) -> int:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be an integer 0 or 1, got {raw!r}") from exc
    if value < 0 or value > MAX_ALLOWED_RETRIES:
        raise SettingsError(
            f"{name} must be 0 or 1 (the extractor does not retry more than once), "
            f"got {raw!r}"
        )
    return value


def _positive_int(name: str, default: int, maximum: int) -> int:
    """Parse a positive integer in ``1..maximum``.

    ``int()`` already rejects non-integers, including ``inf`` and ``nan``
    strings, so a separate ``math.isfinite`` check is not needed here.
    The range check is the capacity equivalent of the timeout/retry limits.
    """
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a positive integer, got {raw!r}") from exc
    if value < 1 or value > maximum:
        raise SettingsError(
            f"{name} must be an integer between 1 and {maximum}, got {raw!r}"
        )
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated process settings for this process."""

    llm_provider: str
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_retry_backoff_seconds: float
    groq_model: str
    gemini_model: str
    groq_base_url: str
    gemini_base_url: str
    groq_api_key: str
    gemini_api_key: str
    event_store_capacity: int

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from the current environment.

        Empty optional strings stay empty. A bad timeout or retry cap raises
        ``SettingsError`` so a typo cannot silently become a 60-second hang.
        An unknown ``LLM_PROVIDER`` is kept (the chain falls back to rules)
        rather than refusing to boot; only numeric limits are hard errors.
        A missing event-store capacity uses the issue default. A typo, zero,
        or a value above the documented ceiling raises ``SettingsError``.
        """
        provider = _raw(ENV_LLM_PROVIDER, DEFAULT_LLM_PROVIDER).lower() or DEFAULT_LLM_PROVIDER
        model_override = _raw(ENV_LLM_MODEL)
        groq_model = model_override or _raw(ENV_GROQ_MODEL, DEFAULT_GROQ_MODEL)
        gemini_model = model_override or _raw(ENV_GEMINI_MODEL, DEFAULT_GEMINI_MODEL)
        # A process-wide LLM_MODEL should only override the active provider.
        if model_override:
            if provider == "gemini":
                groq_model = _raw(ENV_GROQ_MODEL, DEFAULT_GROQ_MODEL)
            elif provider == "groq":
                gemini_model = _raw(ENV_GEMINI_MODEL, DEFAULT_GEMINI_MODEL)
        return cls(
            llm_provider=provider,
            llm_timeout_seconds=_positive_float(
                ENV_LLM_TIMEOUT_SECONDS, DEFAULT_LLM_TIMEOUT_SECONDS
            ),
            llm_max_retries=_retry_count(ENV_LLM_MAX_RETRIES, DEFAULT_LLM_MAX_RETRIES),
            llm_retry_backoff_seconds=_non_negative_float(
                ENV_LLM_RETRY_BACKOFF_SECONDS, DEFAULT_LLM_RETRY_BACKOFF_SECONDS
            ),
            groq_model=groq_model or DEFAULT_GROQ_MODEL,
            gemini_model=gemini_model or DEFAULT_GEMINI_MODEL,
            groq_base_url=_raw(ENV_GROQ_BASE_URL, DEFAULT_GROQ_BASE_URL).rstrip("/")
            or DEFAULT_GROQ_BASE_URL,
            gemini_base_url=_raw(ENV_GEMINI_BASE_URL, DEFAULT_GEMINI_BASE_URL).rstrip("/")
            or DEFAULT_GEMINI_BASE_URL,
            groq_api_key=_raw(ENV_GROQ_API_KEY),
            gemini_api_key=_raw(ENV_GEMINI_API_KEY),
            event_store_capacity=_positive_int(
                ENV_EVENT_STORE_CAPACITY,
                DEFAULT_EVENT_STORE_CAPACITY,
                MAX_EVENT_STORE_CAPACITY,
            ),
        )

    def key_for(self, provider: str) -> str:
        """Return the API key for ``provider``, or an empty string."""
        if provider == "groq":
            return self.groq_api_key
        if provider == "gemini":
            return self.gemini_api_key
        return ""

    def key_env_name(self, provider: str) -> str:
        """Return the environment variable name that holds the provider key."""
        if provider == "groq":
            return ENV_GROQ_API_KEY
        if provider == "gemini":
            return ENV_GEMINI_API_KEY
        raise SettingsError(f"provider {provider!r} has no API key")

    def model_for(self, provider: str) -> str:
        """Return the configured model id for ``provider``."""
        if provider == "groq":
            return self.groq_model
        if provider == "gemini":
            return self.gemini_model
        raise SettingsError(f"provider {provider!r} has no model")

    def base_url_for(self, provider: str) -> str:
        """Return the configured API base URL for ``provider``."""
        if provider == "groq":
            return self.groq_base_url
        if provider == "gemini":
            return self.gemini_base_url
        raise SettingsError(f"provider {provider!r} has no base URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings for this process."""
    return Settings.from_env()


def clear_settings_cache() -> None:
    """Drop the cached settings. Tests call this after changing the env."""
    get_settings.cache_clear()
