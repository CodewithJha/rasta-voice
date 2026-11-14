"""Real dispatcher CSRF handshake, session binding and unsafe-route enforcement."""


import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from starlette.requests import Request

from rasta.dispatch_auth import (
    COOKIE_CSRF,
    COOKIE_SESSION,
    COOKIE_UNLOCK_CSRF,
    HEADER_CSRF,
    attach_dispatch_auth,
    cookie_secure,
    enforce_desk_csrf,
    mint_unlock_csrf,
    unlock_csrf_ok,
)
from rasta.main import app
from rasta.security import SecuredApp
from rasta.settings import clear_settings_cache

SECRET = "synthetic-csrf-desk-fixture"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("DISPATCH_PASSCODE", SECRET)
    monkeypatch.setenv("RASTA_ENV", "development")
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "false")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    yield
    clear_settings_cache()


def challenge(client):
    response = client.get("/api/dispatch/csrf")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    return response.json()["csrf_token"]


def unlock(client):
    token = challenge(client)
    response = client.post(
        "/api/dispatch/unlock", json={"passcode": SECRET}, headers={HEADER_CSRF: token}
    )
    assert response.status_code == 200
    assert COOKIE_UNLOCK_CSRF not in client.cookies
    return client.cookies.get(COOKIE_CSRF)


def test_unlock_rejects_missing_forged_and_cross_site_tokens():
    with TestClient(app) as client:
        assert client.post("/api/dispatch/unlock", json={"passcode": SECRET}).status_code == 403
        token = challenge(client)
        for value in ("forged", token[:-1] + ("a" if token[-1] != "a" else "b")):
            assert (
                client.post(
                    "/api/dispatch/unlock", json={"passcode": SECRET}, headers={HEADER_CSRF: value}
                ).status_code
                == 403
            )
        for extra in (
            {"Origin": "https://hostile.invalid"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
            {"Sec-Fetch-Site": "same-site"},
        ):
            response = client.post(
                "/api/dispatch/unlock",
                json={"passcode": SECRET},
                headers={HEADER_CSRF: token, **extra},
            )
            assert response.status_code == 403
            assert COOKIE_SESSION not in client.cookies
        response = client.post(
            "/api/dispatch/unlock",
            json={"passcode": SECRET},
            headers={HEADER_CSRF: token, "Origin": "http://testserver"},
        )
        assert response.status_code == 200


def test_signed_challenge_expiry_tampering_and_secret_rotation():
    def request(token, cookie=None):
        return Request(
            {
                "type": "http",
                "headers": [
                    (b"x-dispatch-csrf", token.encode()),
                    (b"cookie", f"{COOKIE_UNLOCK_CSRF}={cookie or token}".encode()),
                ],
            }
        )

    token = mint_unlock_csrf(SECRET, now=1000)
    assert unlock_csrf_ok(request(token), SECRET, now=1000)
    assert unlock_csrf_ok(request(token), SECRET, now=1300)
    assert not unlock_csrf_ok(request(token), SECRET, now=1301)
    assert not unlock_csrf_ok(request(token), SECRET, now=999)
    assert not unlock_csrf_ok(request(token), "rotated", now=1001)
    for malformed in ("", "not.a.token", "nan." + "a" * 43 + ".b", "x" * 161):
        assert not unlock_csrf_ok(request(malformed), SECRET, now=1000)
    assert not unlock_csrf_ok(request(token, "different-cookie"), SECRET, now=1001)


@pytest.mark.parametrize(
    "path", ["/api/events/probe", "/api/admin/probe", "/api/dispatch/probe", "/api/v1/events/probe"]
)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_global_guard_covers_future_unsafe_routes_and_binds_sessions(path, method):
    probe = SecuredApp(dependencies=[Depends(enforce_desk_csrf)])
    probe.add_api_route(path, lambda: {"ok": True}, methods=[method])
    with TestClient(app) as first, TestClient(app) as second:
        first_csrf = unlock(first)
        second_csrf = unlock(second)
        first_session = first.cookies.get(COOKIE_SESSION)
        assert first_csrf != second_csrf
        with TestClient(probe) as client:
            client.cookies.set(COOKIE_SESSION, first_session)
            client.cookies.set(COOKIE_CSRF, first_csrf)
            assert client.request(method, path).status_code == 403
            assert (
                client.request(method, path, headers={HEADER_CSRF: first_csrf}).status_code == 200
            )
            # Matching double-submit values from another session cannot authorize this one.
            client.cookies.set(COOKIE_CSRF, second_csrf)
            assert (
                client.request(method, path, headers={HEADER_CSRF: second_csrf}).status_code == 403
            )
            assert (
                client.request(method, path, headers={"X-Dispatch-Passcode": "  "}).status_code
                == 403
            )
            assert (
                client.request(method, path, headers={"X-Dispatch-Passcode": SECRET}).status_code
                == 200
            )
            assert (
                client.request(
                    method,
                    path,
                    headers={"X-Dispatch-Passcode": SECRET, "Origin": "https://hostile.invalid"},
                ).status_code
                == 403
            )


def test_unlock_header_requires_a_valid_credential():
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/dispatch/unlock",
                json={"passcode": SECRET},
                headers={"X-Dispatch-Passcode": "invalid"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/dispatch/unlock",
                json={"passcode": SECRET},
                headers={"X-Dispatch-Passcode": SECRET},
            ).status_code
            == 200
        )


def test_cookies_use_only_trusted_https_or_production(monkeypatch):
    def request():
        return Request(
            {"type": "http", "scheme": "http", "headers": [(b"x-forwarded-proto", b"https")]}
        )

    assert not cookie_secure(request())
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "true")
    clear_settings_cache()
    assert cookie_secure(request())
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "false")
    monkeypatch.setenv("RASTA_ENV", "production")
    clear_settings_cache()
    assert cookie_secure(request())
