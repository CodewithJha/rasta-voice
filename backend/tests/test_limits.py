"""Public speech budget and per-IP caps do not spend when they reject."""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rasta.errors import ContractApp
from rasta.limits import (
    BUDGET,
    BUSY,
    PAUSED,
    RATE,
    SpeechBudgetMiddleware,
    SpeechGuard,
    attach_speech_guard,
    client_ip,
    speech_cost,
)
from rasta.settings import SettingsError, clear_settings_cache, get_settings


@asynccontextmanager
async def _lifespan(app: FastAPI):
    attach_speech_guard(app, replace=True)
    yield


def _probe() -> FastAPI:
    app = ContractApp(lifespan=_lifespan)
    app.add_middleware(SpeechBudgetMiddleware)

    @app.post("/api/ingest/sample")
    def sample() -> dict:
        return {"ok": True, "calls": 2}

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app


def test_speech_costs_are_fixed():
    assert speech_cost("POST", "/api/ingest/sample") == 2
    assert speech_cost("POST", "/api/ingest") == 1
    assert speech_cost("POST", "/api/simulate") == 1
    assert speech_cost("POST", "/api/reply/abc") == 1
    assert speech_cost("WEBSOCKET", "/api/stream") == 1
    assert speech_cost("GET", "/api/health") is None
    assert speech_cost("GET", "/api/events") is None


def test_zero_budget_pauses_speech_and_leaves_health_open(monkeypatch):
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "0")
    clear_settings_cache()
    with TestClient(_probe()) as client:
        denied = client.post("/api/ingest/sample")
        assert denied.status_code == 503
        assert denied.json()["error"]["message"] == PAUSED
        assert client.get("/api/health").json() == {"ok": True}
    clear_settings_cache()


def test_spent_budget_returns_503_without_running_the_route(monkeypatch):
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "2")
    monkeypatch.setenv("RASTA_ENV", "development")
    clear_settings_cache()
    with TestClient(_probe()) as client:
        assert client.post("/api/ingest/sample").json() == {"ok": True, "calls": 2}
        denied = client.post("/api/ingest/sample")
        assert denied.status_code == 503
        assert denied.json()["error"]["message"] == BUDGET
    clear_settings_cache()


def test_per_ip_cap_returns_429(monkeypatch):
    monkeypatch.setenv("RASTA_PER_IP_REQUESTS_PER_MINUTE", "1")
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "40")
    clear_settings_cache()
    with TestClient(_probe()) as client:
        assert client.post("/api/ingest/sample").status_code == 200
        denied = client.post("/api/ingest/sample")
        assert denied.status_code == 429
        assert denied.json()["error"]["message"] == RATE
    clear_settings_cache()


def test_forwarded_for_is_ignored_unless_trust_is_enabled(monkeypatch):
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "false")
    clear_settings_cache()
    settings = get_settings()
    scope = {
        "type": "http",
        "client": ("203.0.113.10", 1234),
        "headers": [(b"x-forwarded-for", b"198.51.100.7")],
    }
    assert client_ip(scope, settings) == "203.0.113.10"
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "true")
    clear_settings_cache()
    settings = get_settings()
    assert client_ip(scope, settings) == "198.51.100.7"
    clear_settings_cache()


def test_production_defaults_and_required_secrets(monkeypatch):
    monkeypatch.setenv("RASTA_ENV", "production")
    monkeypatch.delenv("RASTA_DEMO_SPEECH_BUDGET", raising=False)
    monkeypatch.delenv("RASTA_PER_IP_REQUESTS_PER_MINUTE", raising=False)
    monkeypatch.delenv("RASTA_MAX_CONCURRENT_SPEECH", raising=False)
    monkeypatch.delenv("DISPATCH_PASSCODE", raising=False)
    monkeypatch.delenv("RASTA_ALLOWED_HOSTS", raising=False)
    clear_settings_cache()
    settings = get_settings()
    assert settings.is_production
    assert settings.demo_speech_budget == 40
    assert settings.per_ip_requests_per_minute == 10
    assert settings.max_concurrent_speech == 2
    try:
        settings.require_production_secrets()
        raise AssertionError("missing prod secrets must fail")
    except SettingsError as exc:
        assert "DISPATCH_PASSCODE" in str(exc)
    monkeypatch.setenv("DISPATCH_PASSCODE", "desk-secret")
    clear_settings_cache()
    try:
        get_settings().require_production_secrets()
        raise AssertionError("missing hosts must fail")
    except SettingsError as exc:
        assert "RASTA_ALLOWED_HOSTS" in str(exc)
    monkeypatch.setenv("RASTA_ALLOWED_HOSTS", "localhost,.hf.space")
    clear_settings_cache()
    get_settings().require_production_secrets()
    hosts = get_settings().allowed_hosts
    assert hosts == ("localhost", "*.hf.space")
    clear_settings_cache()


def test_star_is_rejected_in_allowed_hosts(monkeypatch):
    monkeypatch.setenv("RASTA_ALLOWED_HOSTS", "localhost,*")
    clear_settings_cache()
    try:
        get_settings()
        raise AssertionError("wildcard hosts must fail")
    except SettingsError as exc:
        assert "RASTA_ALLOWED_HOSTS" in str(exc)
    clear_settings_cache()


def test_guard_tracks_remaining_calls(monkeypatch):
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "3")
    clear_settings_cache()
    guard = SpeechGuard(get_settings())
    assert guard.remaining() == 3
    assert guard.admit("1.1.1.1", 2) is None
    assert guard.remaining() == 1
    denied = guard.admit("1.1.1.1", 2)
    assert denied is not None and denied.status == 503
    clear_settings_cache()


def test_http_concurrency_cap_returns_busy(monkeypatch):
    monkeypatch.setenv("RASTA_MAX_CONCURRENT_SPEECH", "1")
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "40")
    clear_settings_cache()
    guard = SpeechGuard(get_settings())
    assert guard.admit("1.1.1.1", 1) is None
    denied = guard.admit("2.2.2.2", 1)
    assert denied is not None and denied.status == 503
    assert denied.message == BUSY
    guard.release_slot()
    assert guard.admit("2.2.2.2", 1) is None
    clear_settings_cache()


def test_trusted_hosts_reject_unknown_host():
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    app = FastAPI()
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "*.hf.space"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 400
        allowed = client.get("/api/health", headers={"host": "localhost"})
        assert allowed.status_code == 200
        assert allowed.json() == {"ok": True}
        space = client.get("/api/health", headers={"host": "rasta-demo.hf.space"})
        assert space.status_code == 200
        assert space.json() == {"ok": True}
        other = client.get("/api/health", headers={"host": "evil.example"})
        assert other.status_code == 400


def test_timeout_keeps_concurrency_slot_until_worker_finishes(monkeypatch):
    from fastapi import HTTPException

    from rasta.limits import await_held_work

    monkeypatch.setenv("RASTA_MAX_CONCURRENT_SPEECH", "1")
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "40")
    monkeypatch.setenv("RASTA_PER_IP_REQUESTS_PER_MINUTE", "100")
    clear_settings_cache()
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    hold_workers = True

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        attach_speech_guard(app, replace=True)
        yield

    app = ContractApp(lifespan=lifespan)
    app.add_middleware(SpeechBudgetMiddleware)

    @app.post("/api/ingest/sample")
    async def sample() -> dict:
        def work() -> dict:
            started.set()
            if hold_workers:
                release.wait(timeout=2)
            finished.set()
            return {"ok": True, "calls": 2}

        try:
            return await await_held_work(work, 0.05)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="timed out") from exc

    with TestClient(app) as client:
        first = client.post("/api/ingest/sample")
        assert first.status_code == 504
        assert started.is_set()
        second = client.post("/api/ingest/sample")
        assert second.status_code == 503
        assert second.json()["error"]["message"] == BUSY
        release.set()
        assert finished.wait(timeout=2)
        hold_workers = False
        third = client.post("/api/ingest/sample")
        assert third.status_code == 200
        assert third.json() == {"ok": True, "calls": 2}
    clear_settings_cache()
