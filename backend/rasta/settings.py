"""Typed process settings loaded from the environment.

Issue 02 owns the LLM keys, model ids, timeout, and retry cap. Issue 04
owns the in-memory event-store capacity. Issue 07 owns the realtime
stream limits, timeouts, frame size, and CORS origin allow list. Issue 20
owns the dispatcher passcode and unlock lockout. Issue 21 owns the
structured log line size cap. Issue 13 owns the production environment,
trusted hosts, static dir, public speech budget, and per-IP cap. Call
``get_settings()`` rather
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
ENV_RASTA_MAX_STREAMS = "RASTA_MAX_STREAMS"
ENV_STREAM_SESSION_SECONDS = "RASTA_STREAM_SESSION_SECONDS"
ENV_STREAM_IDLE_SECONDS = "RASTA_STREAM_IDLE_SECONDS"
ENV_STREAM_HEARTBEAT_SECONDS = "RASTA_STREAM_HEARTBEAT_SECONDS"
ENV_STREAM_DRAIN_SECONDS = "RASTA_STREAM_DRAIN_SECONDS"
ENV_STREAM_QUIET_SECONDS = "RASTA_STREAM_QUIET_SECONDS"
ENV_STREAM_FRAME_BYTES = "RASTA_STREAM_FRAME_BYTES"
ENV_STREAM_QUEUE_MAX = "RASTA_STREAM_QUEUE_MAX"
ENV_STREAM_SAMPLE_RATE = "RASTA_STREAM_SAMPLE_RATE"
ENV_CORS_ALLOW_ORIGINS = "CORS_ALLOW_ORIGINS"
ENV_DISPATCH_PASSCODE = "DISPATCH_PASSCODE"
ENV_DISPATCH_UNLOCK_MAX_FAILURES = "DISPATCH_UNLOCK_MAX_FAILURES"
ENV_DISPATCH_UNLOCK_WINDOW_SECONDS = "DISPATCH_UNLOCK_WINDOW_SECONDS"
ENV_LOG_LINE_MAX_BYTES = "RASTA_LOG_LINE_MAX_BYTES"
ENV_RASTA_ENV = "RASTA_ENV"
ENV_RASTA_ALLOWED_HOSTS = "RASTA_ALLOWED_HOSTS"
ENV_RASTA_STATIC_DIR = "RASTA_STATIC_DIR"
ENV_DEMO_SPEECH_BUDGET = "RASTA_DEMO_SPEECH_BUDGET"
ENV_DEMO_SPEECH_WINDOW_SECONDS = "RASTA_DEMO_SPEECH_WINDOW_SECONDS"
ENV_PER_IP_REQUESTS_PER_MINUTE = "RASTA_PER_IP_REQUESTS_PER_MINUTE"
ENV_TRUST_PROXY_HEADERS = "RASTA_TRUST_PROXY_HEADERS"
ENV_MAX_SPEECH_SECONDS = "RASTA_MAX_SPEECH_SECONDS"
ENV_MAX_CONCURRENT_SPEECH = "RASTA_MAX_CONCURRENT_SPEECH"

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

# Issue 07 realtime stream. Defaults match the Prisma session cap, idle
# default, and 1024-byte frame size from the current streaming docs.
DEFAULT_MAX_STREAMS = 2
MAX_MAX_STREAMS = 32
DEFAULT_STREAM_SESSION_SECONDS = 900.0
MAX_STREAM_SESSION_SECONDS = 3600.0
DEFAULT_STREAM_IDLE_SECONDS = 60.0
MAX_STREAM_IDLE_SECONDS = 900.0
DEFAULT_STREAM_HEARTBEAT_SECONDS = 20.0
MAX_STREAM_HEARTBEAT_SECONDS = 300.0
DEFAULT_STREAM_DRAIN_SECONDS = 8.0
MAX_STREAM_DRAIN_SECONDS = 60.0
DEFAULT_STREAM_QUIET_SECONDS = 1.0
MAX_STREAM_QUIET_SECONDS = 30.0
DEFAULT_STREAM_FRAME_BYTES = 1024
MAX_STREAM_FRAME_BYTES = 65_536
DEFAULT_STREAM_QUEUE_MAX = 32
MAX_STREAM_QUEUE_MAX = 1024
DEFAULT_STREAM_SAMPLE_RATE = 16000
ALLOWED_STREAM_SAMPLE_RATES = frozenset({8000, 16000, 44100, 48000})
DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://localhost:5173,http://127.0.0.1:5173"
)
# Issue 20 desk unlock lockout. The passcode itself has no default; empty
# means desk routes fail closed with 503.
DEFAULT_DISPATCH_UNLOCK_MAX_FAILURES = 5
MAX_DISPATCH_UNLOCK_MAX_FAILURES = 100
DEFAULT_DISPATCH_UNLOCK_WINDOW_SECONDS = 600.0
MAX_DISPATCH_UNLOCK_WINDOW_SECONDS = 3600.0
DEFAULT_LOG_LINE_MAX_BYTES = 4096
MAX_LOG_LINE_MAX_BYTES = 65_536
ALLOWED_RASTA_ENVS = frozenset({"development", "production"})
DEFAULT_RASTA_ENV = "development"
DEFAULT_DEMO_SPEECH_BUDGET_PRODUCTION = 40
DEFAULT_DEMO_SPEECH_BUDGET_DEVELOPMENT = 10_000
MAX_DEMO_SPEECH_BUDGET = 1_000_000
DEFAULT_DEMO_SPEECH_WINDOW_SECONDS = 86_400.0
MAX_DEMO_SPEECH_WINDOW_SECONDS = 7 * 86_400.0
DEFAULT_PER_IP_REQUESTS_PRODUCTION = 10
DEFAULT_PER_IP_REQUESTS_DEVELOPMENT = 10_000
MAX_PER_IP_REQUESTS_PER_MINUTE = 10_000
DEFAULT_MAX_SPEECH_SECONDS = 30.0
MAX_MAX_SPEECH_SECONDS = 120.0
DEFAULT_MAX_CONCURRENT_SPEECH_PRODUCTION = 2
DEFAULT_MAX_CONCURRENT_SPEECH_DEVELOPMENT = 32
MAX_MAX_CONCURRENT_SPEECH = 32

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


def _bounded_float(name: str, default: float, maximum: float) -> float:
    """Parse a positive finite float no greater than ``maximum``."""
    value = _positive_float(name, default)
    if value > maximum:
        raise SettingsError(
            f"{name} must be a positive number no greater than {maximum}, got {value!r}"
        )
    return value


def _even_positive_int(name: str, default: int, maximum: int) -> int:
    """Parse a positive even integer in ``2..maximum`` (16-bit PCM frame size)."""
    value = _positive_int(name, default, maximum)
    if value % 2:
        raise SettingsError(f"{name} must be an even integer, got {value!r}")
    return value


def _sample_rate(name: str, default: int) -> int:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(
            f"{name} must be one of {sorted(ALLOWED_STREAM_SAMPLE_RATES)}, got {raw!r}"
        ) from exc
    if value not in ALLOWED_STREAM_SAMPLE_RATES:
        raise SettingsError(
            f"{name} must be one of {sorted(ALLOWED_STREAM_SAMPLE_RATES)}, got {raw!r}"
        )
    return value


def _origin_list(name: str, default: str) -> tuple[str, ...]:
    """Comma-separated exact Origins. Unset uses ``default``; empty is an empty list.

    ``*`` is rejected so a typo cannot open the WebSocket to every site.
    Issue 27 reuses this list for HTTP CORS.
    """
    if name in environ:
        raw = environ.get(name, "").strip()
    else:
        raw = default
    if not raw:
        return ()
    origins = tuple(part.strip() for part in raw.split(",") if part.strip())
    if any(origin == "*" for origin in origins):
        raise SettingsError(f"{name} must not contain *")
    return origins




def _bool(name: str, default: bool) -> bool:
    raw = _raw(name)
    if not raw:
        return default
    value = raw.lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise SettingsError(f"{name} must be true or false, got {raw!r}")


def _rasta_env(name: str, default: str) -> str:
    raw = _raw(name, default).lower()
    if raw not in ALLOWED_RASTA_ENVS:
        raise SettingsError(
            f"{name} must be one of {sorted(ALLOWED_RASTA_ENVS)}, got {raw!r}"
        )
    return raw


def _host_list(name: str) -> tuple[str, ...]:
    """Comma-separated hostnames. Empty means the middleware is left off.

    Starlette only treats ``*.example.com`` as a suffix wildcard. A leading
    ``.example.com`` is normalized to that form. A bare ``*`` is rejected so
    a typo cannot disable host checks in production.
    """
    raw = _raw(name)
    if not raw:
        return ()
    hosts: list[str] = []
    for part in raw.split(","):
        host = part.strip().lower()
        if not host:
            continue
        if host == "*":
            raise SettingsError(f"{name} must not contain *")
        if host.startswith(".") and "*" not in host:
            host = f"*{host}"
        if "*" in host:
            if not host.startswith("*.") or "*" in host[1:]:
                raise SettingsError(
                    f"{name} may use a *.example.com suffix, not {part.strip()!r}"
                )
            suffix = host[2:]
            if not suffix or "/" in suffix or ":" in suffix or " " in suffix:
                raise SettingsError(f"{name} has an invalid host pattern {part.strip()!r}")
        hosts.append(host)
    return tuple(hosts)


def _non_negative_int(name: str, default: int, maximum: int) -> int:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(
            f"{name} must be an integer between 0 and {maximum}, got {raw!r}"
        ) from exc
    if value < 0 or value > maximum:
        raise SettingsError(
            f"{name} must be an integer between 0 and {maximum}, got {raw!r}"
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
    max_streams: int
    stream_session_seconds: float
    stream_idle_seconds: float
    stream_heartbeat_seconds: float
    stream_drain_seconds: float
    stream_quiet_seconds: float
    stream_frame_bytes: int
    stream_queue_max: int
    stream_sample_rate: int
    cors_allow_origins: tuple[str, ...]
    dispatch_passcode: str
    dispatch_unlock_max_failures: int
    dispatch_unlock_window_seconds: float
    log_line_max_bytes: int
    rasta_env: str
    allowed_hosts: tuple[str, ...]
    static_dir: str
    demo_speech_budget: int
    demo_speech_window_seconds: float
    per_ip_requests_per_minute: int
    trust_proxy_headers: bool
    max_speech_seconds: float
    max_concurrent_speech: int

    @property
    def is_production(self) -> bool:
        return self.rasta_env == "production"

    def require_production_secrets(self) -> None:
        """Refuse to boot a production process without the desk passcode and hosts."""
        if not self.is_production:
            return
        if not self.dispatch_passcode:
            raise SettingsError("DISPATCH_PASSCODE is required in production")
        if not self.allowed_hosts:
            raise SettingsError("RASTA_ALLOWED_HOSTS is required in production")

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
        env = _rasta_env(ENV_RASTA_ENV, DEFAULT_RASTA_ENV)
        production = env == "production"
        budget_default = (
            DEFAULT_DEMO_SPEECH_BUDGET_PRODUCTION
            if production
            else DEFAULT_DEMO_SPEECH_BUDGET_DEVELOPMENT
        )
        per_ip_default = (
            DEFAULT_PER_IP_REQUESTS_PRODUCTION
            if production
            else DEFAULT_PER_IP_REQUESTS_DEVELOPMENT
        )
        concurrent_default = (
            DEFAULT_MAX_CONCURRENT_SPEECH_PRODUCTION
            if production
            else DEFAULT_MAX_CONCURRENT_SPEECH_DEVELOPMENT
        )
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
            max_streams=_positive_int(
                ENV_RASTA_MAX_STREAMS, DEFAULT_MAX_STREAMS, MAX_MAX_STREAMS
            ),
            stream_session_seconds=_bounded_float(
                ENV_STREAM_SESSION_SECONDS,
                DEFAULT_STREAM_SESSION_SECONDS,
                MAX_STREAM_SESSION_SECONDS,
            ),
            stream_idle_seconds=_bounded_float(
                ENV_STREAM_IDLE_SECONDS,
                DEFAULT_STREAM_IDLE_SECONDS,
                MAX_STREAM_IDLE_SECONDS,
            ),
            stream_heartbeat_seconds=_bounded_float(
                ENV_STREAM_HEARTBEAT_SECONDS,
                DEFAULT_STREAM_HEARTBEAT_SECONDS,
                MAX_STREAM_HEARTBEAT_SECONDS,
            ),
            stream_drain_seconds=_bounded_float(
                ENV_STREAM_DRAIN_SECONDS,
                DEFAULT_STREAM_DRAIN_SECONDS,
                MAX_STREAM_DRAIN_SECONDS,
            ),
            stream_quiet_seconds=_bounded_float(
                ENV_STREAM_QUIET_SECONDS,
                DEFAULT_STREAM_QUIET_SECONDS,
                MAX_STREAM_QUIET_SECONDS,
            ),
            stream_frame_bytes=_even_positive_int(
                ENV_STREAM_FRAME_BYTES,
                DEFAULT_STREAM_FRAME_BYTES,
                MAX_STREAM_FRAME_BYTES,
            ),
            stream_queue_max=_positive_int(
                ENV_STREAM_QUEUE_MAX, DEFAULT_STREAM_QUEUE_MAX, MAX_STREAM_QUEUE_MAX
            ),
            stream_sample_rate=_sample_rate(
                ENV_STREAM_SAMPLE_RATE, DEFAULT_STREAM_SAMPLE_RATE
            ),
            cors_allow_origins=_origin_list(
                ENV_CORS_ALLOW_ORIGINS, DEFAULT_CORS_ALLOW_ORIGINS
            ),
            dispatch_passcode=_raw(ENV_DISPATCH_PASSCODE),
            dispatch_unlock_max_failures=_positive_int(
                ENV_DISPATCH_UNLOCK_MAX_FAILURES,
                DEFAULT_DISPATCH_UNLOCK_MAX_FAILURES,
                MAX_DISPATCH_UNLOCK_MAX_FAILURES,
            ),
            dispatch_unlock_window_seconds=_bounded_float(
                ENV_DISPATCH_UNLOCK_WINDOW_SECONDS,
                DEFAULT_DISPATCH_UNLOCK_WINDOW_SECONDS,
                MAX_DISPATCH_UNLOCK_WINDOW_SECONDS,
            ),
            log_line_max_bytes=_positive_int(
                ENV_LOG_LINE_MAX_BYTES,
                DEFAULT_LOG_LINE_MAX_BYTES,
                MAX_LOG_LINE_MAX_BYTES,
            ),
            rasta_env=env,
            allowed_hosts=_host_list(ENV_RASTA_ALLOWED_HOSTS),
            static_dir=_raw(ENV_RASTA_STATIC_DIR),
            demo_speech_budget=_non_negative_int(
                ENV_DEMO_SPEECH_BUDGET,
                budget_default,
                MAX_DEMO_SPEECH_BUDGET,
            ),
            demo_speech_window_seconds=_bounded_float(
                ENV_DEMO_SPEECH_WINDOW_SECONDS,
                DEFAULT_DEMO_SPEECH_WINDOW_SECONDS,
                MAX_DEMO_SPEECH_WINDOW_SECONDS,
            ),
            per_ip_requests_per_minute=_positive_int(
                ENV_PER_IP_REQUESTS_PER_MINUTE,
                per_ip_default,
                MAX_PER_IP_REQUESTS_PER_MINUTE,
            ),
            trust_proxy_headers=_bool(ENV_TRUST_PROXY_HEADERS, False),
            max_speech_seconds=_bounded_float(
                ENV_MAX_SPEECH_SECONDS,
                DEFAULT_MAX_SPEECH_SECONDS,
                MAX_MAX_SPEECH_SECONDS,
            ),
            max_concurrent_speech=_positive_int(
                ENV_MAX_CONCURRENT_SPEECH,
                concurrent_default,
                MAX_MAX_CONCURRENT_SPEECH,
            ),
        )

    def prisma_idle_timeout_sec(self) -> int:
        """Idle seconds to send as ``x-idle-timeout-sec`` (Prisma range 5–900)."""
        return min(900, max(5, int(round(self.stream_idle_seconds))))

    def frame_seconds(self) -> float:
        """Playback duration of one PCM frame at the configured sample rate."""
        return self.stream_frame_bytes / (2 * self.stream_sample_rate)

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
