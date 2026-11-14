"""Dispatcher passcode for desk routes (issue 20)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from rasta.dispatch_auth import (
    COOKIE_CSRF,
    COOKIE_SESSION,
    HEADER_CSRF,
    HEADER_PASSCODE,
    UnlockLimiter,
    attach_dispatch_auth,
    passcodes_match,
    require_desk_write,
    sign_session,
)
from rasta.main import app
from rasta.settings import (
    DEFAULT_DISPATCH_UNLOCK_MAX_FAILURES,
    DEFAULT_DISPATCH_UNLOCK_WINDOW_SECONDS,
    SettingsError,
    clear_settings_cache,
    get_settings,
)

REPO = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO / "frontend" / "src"
TEST_PASSCODE = "desk-test-passphrase-9f3"
OTHER_PASSCODE = "desk-other-passphrase-4c1"


@pytest.fixture(autouse=True)
def _reset_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def desk_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPATCH_PASSCODE", TEST_PASSCODE)
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    return TEST_PASSCODE


def _client() -> TestClient:
    return TestClient(app)


def _unlock(client: TestClient, **kwargs):
    """Exercise the real pre-auth CSRF handshake for all unlock and lockout cases."""
    challenge = client.get("/api/dispatch/csrf")
    headers = dict(kwargs.pop("headers", {}))
    if challenge.status_code == 200:
        headers[HEADER_CSRF] = challenge.json()["csrf_token"]
    return client.post("/api/dispatch/unlock", headers=headers, **kwargs)


def test_passcodes_are_compared_as_equal_length_digests():
    assert passcodes_match("gate-key", "gate-key") is True
    assert passcodes_match("gate-key", "gate-kez") is False
    assert passcodes_match("short", "a-much-longer-secret") is False


def test_lockout_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DISPATCH_PASSCODE", raising=False)
    monkeypatch.delenv("DISPATCH_UNLOCK_MAX_FAILURES", raising=False)
    monkeypatch.delenv("DISPATCH_UNLOCK_WINDOW_SECONDS", raising=False)
    clear_settings_cache()
    settings = get_settings()
    assert settings.dispatch_passcode == ""
    assert settings.dispatch_unlock_max_failures == DEFAULT_DISPATCH_UNLOCK_MAX_FAILURES
    assert settings.dispatch_unlock_window_seconds == DEFAULT_DISPATCH_UNLOCK_WINDOW_SECONDS
    assert DEFAULT_DISPATCH_UNLOCK_MAX_FAILURES == 5
    assert DEFAULT_DISPATCH_UNLOCK_WINDOW_SECONDS == 600.0

    monkeypatch.setenv("DISPATCH_PASSCODE", TEST_PASSCODE)
    monkeypatch.setenv("DISPATCH_UNLOCK_MAX_FAILURES", "7")
    monkeypatch.setenv("DISPATCH_UNLOCK_WINDOW_SECONDS", "30")
    clear_settings_cache()
    settings = get_settings()
    assert settings.dispatch_passcode == TEST_PASSCODE
    assert settings.dispatch_unlock_max_failures == 7
    assert settings.dispatch_unlock_window_seconds == 30.0


@pytest.mark.parametrize(
    "name,raw",
    [
        ("DISPATCH_UNLOCK_MAX_FAILURES", "0"),
        ("DISPATCH_UNLOCK_MAX_FAILURES", "abc"),
        ("DISPATCH_UNLOCK_WINDOW_SECONDS", "-1"),
        ("DISPATCH_UNLOCK_WINDOW_SECONDS", "inf"),
    ],
)
def test_lockout_settings_reject_invalid(monkeypatch: pytest.MonkeyPatch, name: str, raw: str):
    monkeypatch.setenv(name, raw)
    clear_settings_cache()
    with pytest.raises(SettingsError, match=name):
        get_settings()


def test_missing_passcode_makes_desk_routes_503(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DISPATCH_PASSCODE", raising=False)
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    with _client() as client:
        listed = client.get("/api/events")
        assert listed.status_code == 503
        assert listed.json()["error"]["message"] == "DISPATCH_PASSCODE is not set"
        unlocked = _unlock(client, json={"passcode": "guess"})
        assert unlocked.status_code == 503
        assert unlocked.json()["error"]["message"] == "DISPATCH_PASSCODE is not set"
        assert "guess" not in unlocked.text


def test_unlock_sets_cookie_and_lists_events(desk_env):
    with _client() as client:
        denied = client.get("/api/events")
        assert denied.status_code == 401
        assert denied.json()["error"]["message"] == "Unlock the desk to keep polling."
        assert TEST_PASSCODE not in denied.text

        wrong = _unlock(client, json={"passcode": OTHER_PASSCODE})
        assert wrong.status_code == 401
        assert OTHER_PASSCODE not in wrong.text
        assert TEST_PASSCODE not in wrong.text
        assert COOKIE_SESSION not in wrong.cookies

        unlocked = _unlock(client, json={"passcode": TEST_PASSCODE})
        assert unlocked.status_code == 200
        assert unlocked.json() == {"ok": True}
        assert TEST_PASSCODE not in unlocked.text
        assert TEST_PASSCODE not in unlocked.headers.get("set-cookie", "")
        session = unlocked.cookies.get(COOKIE_SESSION)
        assert session
        assert session.startswith("d_")
        csrf = unlocked.cookies.get(COOKIE_CSRF)
        assert csrf
        set_cookie = unlocked.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "path=/" in set_cookie
        # TestClient is HTTP, so Secure must stay off.
        assert "secure" not in set_cookie

        listed = client.get("/api/events")
        assert listed.status_code == 200
        assert listed.json() == {"events": [], "next_page_token": None}


def test_header_lists_events_without_a_cookie(desk_env):
    with _client() as client:
        listed = client.get("/api/events", headers={HEADER_PASSCODE: TEST_PASSCODE})
        assert listed.status_code == 200
        assert listed.json() == {"events": [], "next_page_token": None}
        wrong = client.get("/api/events", headers={HEADER_PASSCODE: OTHER_PASSCODE})
        assert wrong.status_code == 401
        assert OTHER_PASSCODE not in wrong.text


def test_rotated_passcode_rejects_old_cookies(desk_env, monkeypatch: pytest.MonkeyPatch):
    with _client() as client:
        unlocked = _unlock(client, json={"passcode": TEST_PASSCODE})
        assert unlocked.status_code == 200
        monkeypatch.setenv("DISPATCH_PASSCODE", OTHER_PASSCODE)
        clear_settings_cache()
        listed = client.get("/api/events")
        assert listed.status_code == 401


def test_fifth_failures_then_lockout_skips_compare(desk_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPATCH_UNLOCK_MAX_FAILURES", "5")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    with _client() as client:
        for attempt in range(5):
            response = _unlock(client, json={"passcode": OTHER_PASSCODE})
            assert response.status_code == 401, attempt
            assert OTHER_PASSCODE not in response.text
        locked = _unlock(client, json={"passcode": OTHER_PASSCODE})
        assert locked.status_code == 429
        assert OTHER_PASSCODE not in locked.text
        # Even the correct passcode stays locked for this address until the window.
        still = _unlock(client, json={"passcode": TEST_PASSCODE})
        assert still.status_code == 429


def test_header_guesses_share_the_unlock_lockout(desk_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPATCH_UNLOCK_MAX_FAILURES", "5")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    compares: list[int] = []
    real = passcodes_match

    def counted(presented: str, expected: str) -> bool:
        compares.append(1)
        return real(presented, expected)

    monkeypatch.setattr("rasta.dispatch_auth.passcodes_match", counted)
    with _client() as client:
        for attempt in range(5):
            response = client.get("/api/events", headers={HEADER_PASSCODE: OTHER_PASSCODE})
            assert response.status_code == 401, attempt
        locked = client.get("/api/events", headers={HEADER_PASSCODE: OTHER_PASSCODE})
        assert locked.status_code == 429
        assert OTHER_PASSCODE not in locked.text
        assert (
            client.get("/api/events", headers={HEADER_PASSCODE: TEST_PASSCODE}).status_code == 429
        )
        assert _unlock(client, json={"passcode": TEST_PASSCODE}).status_code == 429
    assert len(compares) == 5


def test_unlock_failures_also_lock_the_header_path(desk_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPATCH_UNLOCK_MAX_FAILURES", "5")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    with _client() as client:
        for attempt in range(5):
            assert _unlock(client, json={"passcode": OTHER_PASSCODE}).status_code == 401, attempt
        assert (
            client.get("/api/events", headers={HEADER_PASSCODE: OTHER_PASSCODE}).status_code == 429
        )
        assert (
            client.get("/api/events", headers={HEADER_PASSCODE: TEST_PASSCODE}).status_code == 429
        )


def test_valid_cookie_still_works_when_guesses_are_locked(
    desk_env, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DISPATCH_UNLOCK_MAX_FAILURES", "5")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    with _client() as client:
        unlocked = _unlock(client, json={"passcode": TEST_PASSCODE})
        assert unlocked.status_code == 200
        for attempt in range(5):
            assert (
                client.get("/api/events", headers={HEADER_PASSCODE: OTHER_PASSCODE}).status_code
                == 401
            ), attempt
        assert (
            client.get("/api/events", headers={HEADER_PASSCODE: OTHER_PASSCODE}).status_code == 429
        )
        # Cookie access is not a new shared-secret guess.
        listed = client.get("/api/events")
        assert listed.status_code == 200
        assert listed.json() == {"events": [], "next_page_token": None}


def test_concurrent_wrong_unlocks_do_not_exceed_the_cap(desk_env, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPATCH_UNLOCK_MAX_FAILURES", "5")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    compares: list[int] = []
    real = passcodes_match

    def counted(presented: str, expected: str) -> bool:
        compares.append(1)
        return real(presented, expected)

    monkeypatch.setattr("rasta.dispatch_auth.passcodes_match", counted)

    async def run() -> list[int]:
        transport = httpx.ASGITransport(app=app, client=("203.0.113.8", 50000))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            challenge = await client.get("/api/dispatch/csrf")
            assert challenge.status_code == 200
            token = challenge.json()["csrf_token"]

            async def one() -> int:
                response = await client.post(
                    "/api/dispatch/unlock",
                    json={"passcode": OTHER_PASSCODE},
                    headers={HEADER_CSRF: token},
                )
                return response.status_code

            return list(await asyncio.gather(*[one() for _ in range(10)]))

    codes = asyncio.run(run())
    assert codes.count(401) == 5, codes
    assert codes.count(429) == 5, codes
    assert len(compares) == 5


def test_successful_unlock_clears_lockout(desk_env):
    with _client() as client:
        for _ in range(2):
            assert _unlock(client, json={"passcode": OTHER_PASSCODE}).status_code == 401
        assert _unlock(client, json={"passcode": TEST_PASSCODE}).status_code == 200
        assert _unlock(client, json={"passcode": OTHER_PASSCODE}).status_code == 401


def test_cookie_alone_is_not_enough_to_write(desk_env):
    probe = FastAPI()

    @probe.post("/api/dispatch/probe")
    def probe_write(actor: str = Depends(require_desk_write)) -> dict:
        return {"actor": actor}

    with _client() as source:
        unlocked = _unlock(source, json={"passcode": TEST_PASSCODE})
        assert unlocked.status_code == 200
        session = unlocked.cookies.get(COOKIE_SESSION)
        csrf = unlocked.cookies.get(COOKIE_CSRF)
        assert session and csrf

    with TestClient(probe) as client:
        cookie_only = client.post("/api/dispatch/probe", cookies={COOKIE_SESSION: session})
        assert cookie_only.status_code == 403
        matched = client.post(
            "/api/dispatch/probe",
            cookies={COOKIE_SESSION: session, COOKIE_CSRF: csrf},
            headers={HEADER_CSRF: csrf},
        )
        assert matched.status_code == 200
        assert matched.json()["actor"].startswith("d_")
        header = client.post("/api/dispatch/probe", headers={HEADER_PASSCODE: TEST_PASSCODE})
        assert header.status_code == 200
        assert header.json()["actor"] == "d_header"


def test_rider_ingest_stays_public(desk_env, monkeypatch: pytest.MonkeyPatch):
    # A missing key still proves the route is reachable without the desk cookie.
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with _client() as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        payload = health.json()
        assert TEST_PASSCODE not in str(payload)
        assert "DISPATCH_PASSCODE" not in str(payload)
        assert "dispatch_passcode" not in str(payload)
        sample = client.post("/api/ingest/sample")
        assert sample.status_code == 503
        listed = client.get("/api/events")
        assert listed.status_code == 401


def test_passcode_is_absent_from_frontend_source():
    hits = []
    for path in FRONTEND_SRC.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".css", ".html", ".js"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in ("DISPATCH_PASSCODE", TEST_PASSCODE, "X-Dispatch-Passcode"):
            if needle in text:
                hits.append(f"{path.relative_to(REPO)}: {needle}")
    assert hits == []


def test_limiter_blocks_after_the_configured_window_fills():
    limiter = UnlockLimiter()

    class _Settings:
        dispatch_unlock_max_failures = 5
        dispatch_unlock_window_seconds = 10.0

    settings = _Settings()
    now = 100.0
    for offset in range(5):
        limiter.record_failure("1.2.3.4", settings, now=now + offset)
    assert limiter.blocked("1.2.3.4", settings, now=now + 4) is True
    assert limiter.blocked("1.2.3.4", settings, now=now + 14) is False
    assert limiter.blocked("9.9.9.9", settings, now=now + 4) is False


def test_session_signature_changes_with_the_secret():
    actor = "d_" + "ab" * 8
    first = sign_session("one", actor)
    second = sign_session("two", actor)
    assert first != second
    assert first.startswith(actor + ".")
