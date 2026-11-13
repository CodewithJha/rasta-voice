"""Upstream retries, breakers, inflight cap, and shutdown (issue 29)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.errors import GnaniError
from rasta.limits import attach_speech_guard
from rasta.main import app
from rasta.resilience import (
    UPSTREAM_STT,
    CircuitBreaker,
    ResilienceError,
    UpstreamRuntime,
    attach_upstream_runtime,
    classify_failure,
    retry_delay_seconds,
    shutdown_upstream_runtime,
)
from rasta.settings import clear_settings_cache, get_settings
from rasta.store import attach_event_store

LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _stt_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "request_id": "req-1",
            "transcript": LINE,
            "model": "prisma-v3.0",
            "detected_language_code": "hi-IN",
            "processing_time": 0.2,
        },
    )


def _speech_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    monkeypatch.setenv("DISPATCH_PASSCODE", "synthetic-desk-passcode")
    clear_settings_cache()


def _install_transport(transport: httpx.BaseTransport) -> TestClient:
    # Lifespan must start first so the later replace keeps the test transport.
    client = TestClient(app)
    client.__enter__()
    attach_speech_guard(app, replace=True)
    attach_event_store(app, replace=True)
    attach_upstream_runtime(app, replace=True, transport=transport)
    return client


def test_breaker_open_half_open_and_success_closes():
    clock = FakeClock()
    breaker = CircuitBreaker(
        "gnani_stt",
        failure_threshold=5,
        window_seconds=60.0,
        open_seconds=30.0,
        clock=clock,
    )
    for _ in range(5):
        breaker.record_failure()
        clock.advance(1)
    assert breaker.state() == "open"
    assert breaker.allow() is False
    clock.advance(30)
    assert breaker.state() == "half_open"
    assert breaker.allow() is True
    assert breaker.allow() is False
    breaker.record_success()
    assert breaker.state() == "closed"
    assert breaker.allow() is True


def test_half_open_failure_reopens():
    clock = FakeClock()
    breaker = CircuitBreaker(
        "gnani_tts",
        failure_threshold=5,
        window_seconds=60.0,
        open_seconds=30.0,
        clock=clock,
    )
    for _ in range(5):
        breaker.record_failure()
    clock.advance(30)
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.state() == "open"
    assert breaker.allow() is False


def test_five_failures_open_the_breaker_without_a_sixth_call():
    settings = replace(get_settings(), upstream_max_retries=0)
    runtime = UpstreamRuntime(settings, sleeper=lambda _delay: None, rng=lambda: 0.0)
    attempts = {"n": 0}

    def fail() -> None:
        attempts["n"] += 1
        raise GnaniError("STT 503", status=503)

    for _ in range(5):
        with pytest.raises(GnaniError):
            runtime.call_gnani(UPSTREAM_STT, fail)
    assert attempts["n"] == 5
    with pytest.raises(ResilienceError) as err:
        runtime.call_gnani(UPSTREAM_STT, fail)
    assert err.value.code == "circuit_open"
    assert err.value.status == 503
    assert attempts["n"] == 5
    runtime.close()


def test_retry_after_is_capped():
    settings = get_settings()
    assert retry_delay_seconds(1, settings, "9", rng=lambda: 1.0) == 2.0
    assert 0.0 <= retry_delay_seconds(1, settings, rng=lambda: 0.5) <= 0.2


def test_402_is_not_retryable():
    status, retryable = classify_failure(GnaniError("payment", status=402))
    assert status == 402
    assert retryable is False


def test_429_then_success_is_one_ingest_and_two_attempts(
    monkeypatch: pytest.MonkeyPatch, make_wav, caplog: pytest.LogCaptureFixture
):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/stt/v3":
            if seen.count("/stt/v3") == 1:
                return httpx.Response(429, json={"detail": {"message": "slow down"}})
            return _stt_ok()
        raise AssertionError(f"unexpected {request.url.path}")

    _speech_env(monkeypatch)
    client = _install_transport(httpx.MockTransport(handler))
    with caplog.at_level(logging.INFO, logger="rasta"):
        response = client.post(
            "/api/ingest",
            files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
        )
    assert response.status_code == 200
    assert seen == ["/stt/v3", "/stt/v3"]
    assert "test-key" not in caplog.text
    assert "GNANI_API_KEY" not in caplog.text
    body = client.get("/api/ready").json()
    assert body["circuit_breaker"]["gnani_stt"] == "closed"


def test_402_is_not_retried(monkeypatch: pytest.MonkeyPatch, make_wav):
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(402, json={"detail": {"message": "credits"}})

    _speech_env(monkeypatch)
    client = _install_transport(httpx.MockTransport(handler))
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
    )
    assert response.status_code == 502
    assert seen == ["/stt/v3"]


def test_retries_stop_when_the_budget_would_be_exceeded(
    monkeypatch: pytest.MonkeyPatch, make_wav
):
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "1")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(503, json={"detail": {"message": "busy"}})

    _speech_env(monkeypatch)
    client = _install_transport(httpx.MockTransport(handler))
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
    )
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "budget_exhausted"
    assert seen == ["/stt/v3"]


def test_semaphore_wait_timeout_returns_429():
    settings = replace(get_settings(), max_inflight=1, inflight_wait_seconds=0.05)
    runtime = UpstreamRuntime(
        settings,
        sleeper=lambda _delay: None,
        rng=lambda: 0.0,
    )

    started = threading.Event()
    release = threading.Event()

    def hold() -> str:
        started.set()
        release.wait(timeout=2)
        return "ok"

    worker = threading.Thread(target=lambda: runtime.call_gnani(UPSTREAM_STT, hold))
    worker.start()
    assert started.wait(timeout=1)
    with pytest.raises(ResilienceError) as err:
        runtime.call_gnani(UPSTREAM_STT, lambda: "nope")
    assert err.value.status == 429
    assert err.value.code == "too_many_requests"
    release.set()
    worker.join(timeout=2)
    runtime.close()


def test_shutdown_closes_the_client_and_drains():
    from rasta.resilience import set_upstream_runtime

    runtime = UpstreamRuntime(get_settings())
    set_upstream_runtime(runtime)
    app.state.upstream_runtime = runtime
    runtime.bind_app(app)
    assert runtime.client.is_closed is False
    shutdown_upstream_runtime(app)
    assert runtime.accepting is False
    assert runtime.client.is_closed is True
    with pytest.raises(ResilienceError) as err:
        runtime.call_gnani(UPSTREAM_STT, lambda: "nope")
    assert err.value.code == "shutting_down"


def test_health_stays_snappy_while_a_gnani_call_is_in_flight(
    monkeypatch: pytest.MonkeyPatch, make_wav
):
    started = threading.Event()
    release = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        release.wait(timeout=2)
        return _stt_ok()

    _speech_env(monkeypatch)
    client = _install_transport(httpx.MockTransport(handler))
    result: dict[str, int] = {}

    def ingest() -> None:
        response = client.post(
            "/api/ingest",
            files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
        )
        result["status"] = response.status_code

    worker = threading.Thread(target=ingest)
    worker.start()
    assert started.wait(timeout=2)
    t0 = time.perf_counter()
    health = client.get("/api/health")
    elapsed = time.perf_counter() - t0
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert elapsed < 0.5
    release.set()
    worker.join(timeout=2)
    assert result["status"] == 200



def _read_timeout(request: httpx.Request) -> float | None:
    timeout = request.extensions.get("timeout")
    if timeout is None:
        return None
    if isinstance(timeout, dict):
        value = timeout.get("read")
        return float(value) if value is not None else None
    read = getattr(timeout, "read", None)
    return float(read) if read is not None else None


def test_stt_and_tts_posts_use_configured_read_timeouts(make_wav):
    from gnani_client.stt import PrismaSTT
    from gnani_client.tts import TimbreTTS

    settings = get_settings()
    seen: list[tuple[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, _read_timeout(request)))
        if request.url.path == "/stt/v3":
            return _stt_ok()
        if request.url.path == "/api/v1/tts/inference":
            return httpx.Response(200, content=make_wav(seconds=1, rate=16000))
        raise AssertionError(request.url.path)

    runtime = UpstreamRuntime(settings, transport=httpx.MockTransport(handler))
    try:
        PrismaSTT(key="test-key", client=runtime.client).transcribe(make_wav(seconds=1))
        TimbreTTS(key="test-key", client=runtime.client).synthesize("Namaste")
        explicit = runtime.client.post(
            "https://example.invalid/stt/v3",
            timeout=httpx.Timeout(7.0),
        )
        assert explicit.status_code == 200
    finally:
        runtime.close()
    assert seen[0] == ("/stt/v3", settings.stt_read_timeout_seconds)
    assert seen[1] == ("/api/v1/tts/inference", settings.tts_read_timeout_seconds)
    assert seen[2] == ("/stt/v3", 7.0)


def test_retry_after_from_gnani_response_is_honored(make_wav):
    from gnani_client.stt import PrismaSTT

    slept: list[float] = []
    settings = replace(get_settings(), retry_after_cap_seconds=2.0)
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        if len(seen) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
                json={"detail": {"message": "slow down"}},
            )
        return _stt_ok()

    runtime = UpstreamRuntime(
        settings,
        transport=httpx.MockTransport(handler),
        sleeper=slept.append,
        rng=lambda: 1.0,
    )
    try:
        result = runtime.call_gnani(
            UPSTREAM_STT,
            lambda: PrismaSTT(key="test-key", client=runtime.client).transcribe(
                make_wav(seconds=1)
            ),
        )
        assert result.transcript == LINE
    finally:
        runtime.close()
    assert seen == [1, 1]
    assert slept == [2.0]


def test_rejected_half_open_probe_is_released_for_a_later_recovery():
    clock = FakeClock()
    settings = replace(
        get_settings(),
        upstream_max_retries=0,
        max_inflight=1,
        inflight_wait_seconds=0.05,
        breaker_failure_threshold=1,
        breaker_open_seconds=30.0,
    )
    runtime = UpstreamRuntime(
        settings,
        sleeper=lambda _delay: None,
        rng=lambda: 0.0,
        clock=clock,
    )
    with pytest.raises(GnaniError):
        runtime.call_gnani(
            UPSTREAM_STT,
            lambda: (_ for _ in ()).throw(GnaniError("down", status=503)),
        )
    assert runtime.breakers[UPSTREAM_STT].state() == "open"
    clock.advance(31)
    assert runtime.breakers[UPSTREAM_STT].state() == "half_open"
    assert runtime.sema.acquire(timeout=1)

    with pytest.raises(ResilienceError) as err:
        runtime.call_gnani(UPSTREAM_STT, lambda: "probe")
    assert err.value.code == "too_many_requests"
    runtime.sema.release()
    clock.advance(100)
    calls = {"n": 0}

    def ok() -> str:
        calls["n"] += 1
        return "recovered"

    assert runtime.call_gnani(UPSTREAM_STT, ok) == "recovered"
    assert calls["n"] == 1
    assert runtime.breakers[UPSTREAM_STT].state() == "closed"
    runtime.close()


def test_shutdown_waits_out_backoff_and_skips_the_next_attempt():
    from rasta.resilience import set_upstream_runtime

    in_backoff = threading.Event()
    resume = threading.Event()
    calls = {"n": 0}

    def sleeper(_delay: float) -> None:
        in_backoff.set()
        resume.wait(timeout=2)

    def flaky() -> str:
        calls["n"] += 1
        raise GnaniError("busy", status=429)

    settings = replace(get_settings(), upstream_max_retries=2)
    runtime = UpstreamRuntime(settings, sleeper=sleeper, rng=lambda: 1.0)
    set_upstream_runtime(runtime)
    app.state.upstream_runtime = runtime
    runtime.bind_app(app)

    result: dict[str, str] = {}

    def invoke() -> None:
        try:
            runtime.call_gnani(UPSTREAM_STT, flaky)
        except Exception as exc:
            result["code"] = getattr(exc, "code", type(exc).__name__)

    worker = threading.Thread(target=invoke)
    worker.start()
    assert in_backoff.wait(timeout=2)
    # Drain must not return while the accepted call is backing off.
    started = time.perf_counter()
    runtime.begin_shutdown()
    idle = runtime.wait_for_idle(timeout=0.15)
    assert idle is False
    assert time.perf_counter() - started < 0.5
    resume.set()
    worker.join(timeout=2)
    runtime.close()
    assert result["code"] == "shutting_down"
    assert calls["n"] == 1


def test_reply_speech_uses_the_shared_runtime(monkeypatch: pytest.MonkeyPatch, make_wav):
    from rasta.resilience import get_upstream_runtime

    seen: list[float | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(_read_timeout(request))
        return httpx.Response(200, content=make_wav(seconds=1, rate=16000))

    _speech_env(monkeypatch)
    client = _install_transport(httpx.MockTransport(handler))
    store = attach_event_store(app)
    row = store.append(
        {
            "event": {
                "intent": "delay",
                "order_id": "18",
                "eta_minutes": 10,
                "urgency": "medium",
                "dispatch_action": "inform rider",
                "transcript": LINE,
                "confidence": 0.9,
            }
        }
    )
    runtime = get_upstream_runtime()
    assert runtime is not None
    response = client.post(f"/api/reply/{row['id']}")
    assert response.status_code == 200
    assert seen
    assert seen[0] == 15.0
    assert "audio_base64" in response.json()
