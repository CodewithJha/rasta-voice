"""Shared upstream client, retries, breakers, and inflight cap (issue 29)."""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar

import httpx

from gnani_client.errors import GnaniError, MissingApiKeyError
from rasta.request_id import current_request_id
from rasta.settings import Settings, get_settings

log = logging.getLogger("rasta")

T = TypeVar("T")

UPSTREAM_STT = "gnani_stt"
UPSTREAM_TTS = "gnani_tts"
UPSTREAM_LLM = "llm"
UPSTREAMS = (UPSTREAM_STT, UPSTREAM_TTS, UPSTREAM_LLM)
RETRYABLE_STATUS = frozenset({429, 502, 503})

_attach_lock = threading.Lock()
_process_runtime: UpstreamRuntime | None = None


class ResilienceError(Exception):
    """Typed failure for speech routes: HTTP status plus a stable code."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message

    def as_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class CircuitBreaker:
    """One-process breaker: closed, open, then one half-open probe."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        open_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer")
        self.name = name
        self._threshold = failure_threshold
        self._window = window_seconds
        self._open_seconds = open_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: list[float] = []
        self._opened_at: float | None = None
        self._half_open = False
        self._probe_outstanding = False

    def state(self) -> str:
        with self._lock:
            self._refresh_locked(self._clock())
            if self._opened_at is None:
                return "closed"
            if self._half_open:
                return "half_open"
            return "open"

    def is_blocked(self) -> bool:
        """True when a new call must fail fast without claiming a probe."""
        with self._lock:
            now = self._clock()
            self._refresh_locked(now)
            if self._opened_at is None:
                return False
            if self._half_open and not self._probe_outstanding:
                return False
            return True

    def allow(self) -> bool:
        """Return True if one call may start. A half-open probe is exclusive."""
        with self._lock:
            now = self._clock()
            self._refresh_locked(now)
            if self._opened_at is None:
                return True
            if not self._half_open:
                return False
            if self._probe_outstanding:
                return False
            self._probe_outstanding = True
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._opened_at = None
            self._half_open = False
            self._probe_outstanding = False

    def record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            self._probe_outstanding = False
            if self._half_open or self._opened_at is not None:
                self._opened_at = now
                self._half_open = False
                self._failures = [now]
                return
            self._failures = [at for at in self._failures if now - at < self._window]
            self._failures.append(now)
            if len(self._failures) >= self._threshold:
                self._opened_at = now
                self._half_open = False

    def _refresh_locked(self, now: float) -> None:
        if self._opened_at is None or self._half_open:
            return
        if now - self._opened_at >= self._open_seconds:
            self._half_open = True
            self._probe_outstanding = False


class LlmBreakerHook:
    """Adapter so extractors.breaker.ensure_closed reads the real LLM breaker."""

    def __init__(self, breaker: CircuitBreaker) -> None:
        self._breaker = breaker

    def allow(self, name: str) -> bool:
        return not self._breaker.is_blocked()


class UpstreamClient(httpx.Client):
    """One process client that applies per-upstream read timeouts."""

    def __init__(self, settings: Settings, **kwargs: Any) -> None:
        self._rasta_settings = settings
        timeout = httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.batch_read_timeout_seconds,
            write=settings.connect_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        )
        kwargs.setdefault("timeout", timeout)
        super().__init__(**kwargs)

    def request(self, method: str, url: httpx.URL | str, **kwargs: Any) -> httpx.Response:
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout_for(str(url))
        return super().request(method, url, **kwargs)

    def timeout_for(self, url: str) -> httpx.Timeout:
        settings = self._rasta_settings
        read = settings.llm_timeout_seconds
        lowered = url.lower()
        if "/stt/v3/batch" in lowered:
            read = settings.batch_read_timeout_seconds
        elif "/stt/" in lowered:
            read = settings.stt_read_timeout_seconds
        elif "/tts/" in lowered:
            read = settings.tts_read_timeout_seconds
        return httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=read,
            write=settings.connect_timeout_seconds,
            pool=settings.connect_timeout_seconds,
        )


def retry_delay_seconds(
    attempt: int,
    settings: Settings,
    retry_after: str | None = None,
    *,
    rng: Callable[[], float] = random.random,
) -> float:
    """Full-jitter exponential backoff, honoring Retry-After up to the cap."""
    cap = settings.retry_after_cap_seconds
    parsed = _parse_retry_after(retry_after)
    if parsed is not None:
        return min(cap, max(0.0, parsed))
    ceiling = settings.upstream_retry_backoff_seconds * (2 ** max(0, attempt - 1))
    return min(cap, rng() * ceiling)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if when.tzinfo is None:
        return None
    return max(0.0, when.timestamp() - time.time())


def classify_failure(exc: BaseException) -> tuple[int | str, bool]:
    """Return (status, retryable) for an upstream failure."""
    if isinstance(exc, MissingApiKeyError):
        return 503, False
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", True
    if isinstance(exc, httpx.RequestError):
        return "transport", True
    if isinstance(exc, GnaniError):
        status = exc.status
        if status in RETRYABLE_STATUS:
            return status, True
        return status if status is not None else "error", False
    return "error", False


def retry_after_from_error(exc: BaseException) -> str | None:
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    try:
        return headers.get("Retry-After") or headers.get("retry-after")
    except Exception:
        return None


class UpstreamRuntime:
    """Process-wide client, breakers, inflight semaphore, and shutdown gate."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        guard: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self.settings = settings
        self.guard = guard
        self._clock = clock
        self._sleeper = sleeper
        self._rng = rng
        kwargs: dict[str, Any] = {}
        if transport is not None:
            kwargs["transport"] = transport
        self.client = UpstreamClient(settings, **kwargs)
        self.breakers = {
            name: CircuitBreaker(
                name,
                failure_threshold=settings.breaker_failure_threshold,
                window_seconds=settings.breaker_window_seconds,
                open_seconds=settings.breaker_open_seconds,
                clock=clock,
            )
            for name in UPSTREAMS
        }
        self.sema = threading.BoundedSemaphore(settings.max_inflight)
        self.accepting = True
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._app: Any | None = None

    def bind_app(self, app: Any) -> None:
        self._app = app
        self.publish()

    def snapshot(self) -> dict[str, str]:
        return {name: breaker.state() for name, breaker in self.breakers.items()}

    def publish(self) -> None:
        if self._app is not None:
            self._app.state.circuit_breaker = self.snapshot()

    def begin_shutdown(self) -> None:
        self.accepting = False

    def wait_for_idle(self, timeout: float | None = None) -> bool:
        limit = self.settings.shutdown_drain_seconds if timeout is None else timeout
        return self._idle.wait(timeout=limit)

    def close(self) -> None:
        if not self.client.is_closed:
            self.client.close()

    def _acquire_inflight(self) -> bool:
        if not self.sema.acquire(timeout=self.settings.inflight_wait_seconds):
            return False
        with self._inflight_lock:
            self._inflight += 1
            self._idle.clear()
        return True

    def _release_inflight(self) -> None:
        with self._inflight_lock:
            if self._inflight > 0:
                self._inflight -= 1
            if self._inflight == 0:
                self._idle.set()
        self.sema.release()

    def call_gnani(self, upstream: str, func: Callable[[], T]) -> T:
        if not self.accepting:
            raise ResilienceError(
                503, "shutting_down", "The process is shutting down."
            )
        breaker = self.breakers[upstream]
        last_error: BaseException | None = None
        attempts = self.settings.upstream_max_retries + 1
        for attempt in range(1, attempts + 1):
            if not breaker.allow():
                self.publish()
                raise ResilienceError(
                    503, "circuit_open", f"{upstream} circuit is open"
                )
            if attempt > 1 and self.guard is not None:
                decision = self.guard.reserve_budget(1)
                if decision is not None:
                    raise ResilienceError(
                        429,
                        "budget_exhausted",
                        "A retry would exceed the public speech budget.",
                    )
            if not self._acquire_inflight():
                raise ResilienceError(
                    429,
                    "too_many_requests",
                    "Gnani concurrency limit reached; try again shortly.",
                )
            started = time.perf_counter()
            try:
                result = func()
            except Exception as exc:
                status, retryable = classify_failure(exc)
                latency_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
                log.info(
                    "upstream attempt",
                    extra={
                        "request_id": current_request_id(),
                        "attempt": attempt,
                        "status": status,
                        "latency_ms": latency_ms,
                        "upstream": upstream,
                    },
                )
                self._release_inflight()
                if isinstance(exc, MissingApiKeyError):
                    raise
                breaker.record_failure()
                self.publish()
                if retryable and attempt < attempts:
                    delay = retry_delay_seconds(
                        attempt,
                        self.settings,
                        retry_after_from_error(exc),
                        rng=self._rng,
                    )
                    if delay > 0:
                        self._sleeper(delay)
                    last_error = exc
                    continue
                raise
            else:
                latency_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
                log.info(
                    "upstream attempt",
                    extra={
                        "request_id": current_request_id(),
                        "attempt": attempt,
                        "status": 200,
                        "latency_ms": latency_ms,
                        "upstream": upstream,
                    },
                )
                breaker.record_success()
                self.publish()
                self._release_inflight()
                return result
        assert last_error is not None
        raise last_error

    def record_llm_success(self) -> None:
        self.breakers[UPSTREAM_LLM].record_success()
        self.publish()

    def record_llm_failure(self) -> None:
        self.breakers[UPSTREAM_LLM].record_failure()
        self.publish()


def get_upstream_runtime() -> UpstreamRuntime | None:
    return _process_runtime


def set_upstream_runtime(runtime: UpstreamRuntime | None) -> None:
    global _process_runtime
    _process_runtime = runtime


def attach_upstream_runtime(
    app: Any,
    *,
    replace: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> UpstreamRuntime:
    """Create or return the process runtime and attach it to ``app.state``."""
    if not replace:
        runtime = getattr(app.state, "upstream_runtime", None)
        if isinstance(runtime, UpstreamRuntime) and not runtime.client.is_closed:
            return runtime
    with _attach_lock:
        if not replace:
            runtime = getattr(app.state, "upstream_runtime", None)
            if isinstance(runtime, UpstreamRuntime) and not runtime.client.is_closed:
                return runtime
        previous = getattr(app.state, "upstream_runtime", None)
        from rasta.limits import attach_speech_guard

        runtime = UpstreamRuntime(
            get_settings(),
            transport=transport,
            guard=attach_speech_guard(app),
        )
        runtime.bind_app(app)
        app.state.upstream_runtime = runtime
        set_upstream_runtime(runtime)
        try:
            from rasta.extractors.breaker import set_breaker

            set_breaker(LlmBreakerHook(runtime.breakers[UPSTREAM_LLM]))
        except Exception:
            pass
        if previous is not None and previous is not runtime:
            previous.close()
        return runtime


def shutdown_upstream_runtime(app: Any) -> None:
    runtime = getattr(app.state, "upstream_runtime", None)
    if not isinstance(runtime, UpstreamRuntime):
        runtime = _process_runtime
    if runtime is None:
        return
    runtime.begin_shutdown()
    runtime.wait_for_idle()
    runtime.close()
    attached = getattr(getattr(app, "state", None), "upstream_runtime", None)
    if attached is runtime:
        app.state.upstream_runtime = None
    if get_upstream_runtime() is runtime:
        set_upstream_runtime(None)
    try:
        from rasta.extractors.breaker import set_breaker

        set_breaker(None)
    except Exception:
        pass
