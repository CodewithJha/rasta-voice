"""Real combined API/security/privacy boundaries, with test-only cached payloads."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from rasta.dispatch_auth import COOKIE_CSRF, HEADER_CSRF, attach_dispatch_auth
from rasta.http_counts import attach_http_counts
from rasta.idempotency import MAX_IDEMPOTENCY_REQUEST_BYTES, hash_token
from rasta.main import app
from rasta.settings import clear_settings_cache
from rasta.store import EventStore

SECRET = "synthetic-integration-passphrase"
KEY = "synthetic-integrated-cache-key"
ROUTE = "/api/ingest/sample"


@pytest.fixture
def desk(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-only-key")
    monkeypatch.setenv("DISPATCH_PASSCODE", SECRET)
    monkeypatch.setenv("RASTA_ENV", "development")
    clear_settings_cache()
    attach_dispatch_auth(app, replace=True)
    counts = attach_http_counts(app, replace=True)
    now = [datetime(2026, 11, 14, tzinfo=UTC)]
    store = EventStore(2, ":memory:", clock=lambda: now[0], ttl_hours=1)
    monkeypatch.setattr(app.state, "event_store", store, raising=False)

    def no_speech(*args, **kwargs):
        pytest.fail("Cache/denial integration must never start provider work")

    monkeypatch.setattr("rasta.main.speak_sample", no_speech)
    client = TestClient(app)  # Keep the real patched-clock store, without a lifespan replacement.
    yield client, store, now, counts
    client.close()
    store.close()
    clear_settings_cache()


def row(store, text="synthetic transcript"):
    return store.append(
        {
            "transcript": text,
            "event": {
                "intent": "other",
                "order_id": "18",
                "eta_minutes": None,
                "urgency": "low",
                "dispatch_action": "read the transcript",
                "transcript": text,
                "confidence": 0.0,
            },
        }
    )


def cache(store, record):
    payload = json.dumps({"ingest": record, "audio_base64": "synthetic-cache-fixture"}).encode()
    store.remember_idempotency(hash_token(KEY.encode()), ROUTE, hash_token(b"\0"), 200, payload)
    return payload


def unlock(client):
    token = client.get("/api/dispatch/csrf").json()["csrf_token"]
    response = client.post(
        "/api/dispatch/unlock", json={"passcode": SECRET}, headers={HEADER_CSRF: token}
    )
    assert response.status_code == 200
    return {HEADER_CSRF: client.cookies.get(COOKIE_CSRF)}


def test_cookie_delete_and_wipe_need_csrf_and_clear_replay_payloads(desk):
    client, store, _now, _counts = desk
    first = row(store)
    cache(store, first)
    csrf = unlock(client)
    denied = client.delete(f"/api/events/{first['id']}")
    assert denied.status_code == 403
    assert store.get(first["id"]) is not None
    assert client.delete(f"/api/events/{first['id']}", headers=csrf).status_code == 204
    assert store._idempotency_response_bytes == 0
    replay = client.post(ROUTE, headers={"Idempotency-Key": KEY})
    assert replay.status_code == 503
    assert replay.json()["error"]["code"] == "idempotency_response_unavailable"
    second = row(store)
    cache(store, second)
    assert client.post("/api/admin/wipe", json={"confirm": "wipe"}).status_code == 403
    assert client.post("/api/admin/wipe", json={"confirm": "bad"}, headers=csrf).status_code == 422
    assert client.post("/api/admin/wipe", json={"confirm": "wipe"}, headers=csrf).status_code == 204
    assert store._idempotency_response_bytes == 0
    assert store.list_since(None) == []
    # Retain non-sensitive no-repeat metadata, never permit a fresh paid execution.
    assert store._conn.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0] == 1
    assert client.post(ROUTE, headers={"Idempotency-Key": KEY}).status_code == 503


def test_unswept_expiry_is_hidden_from_pagination_and_cached_replay(desk):
    client, store, now, _counts = desk
    old = row(store, "expired synthetic transcript")
    # A late reply is still cached when its older source event reaches TTL.
    now[0] += timedelta(seconds=3595)
    reply_route = f"/api/reply/{old['id']}"
    store.remember_idempotency(
        hash_token(KEY.encode()),
        reply_route,
        hash_token(b"\0"),
        200,
        b'{"text":"expired synthetic reply","audio_base64":"fixture"}',
    )
    now[0] += timedelta(seconds=5)
    fresh = row(store, "fresh synthetic transcript")
    headers = {"X-Dispatch-Passcode": SECRET}
    for path in ("/api/events", "/api/v1/events"):
        response = client.get(path, headers=headers, params={"limit": 1})
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["events"]] == [fresh["id"]]
        assert response.json()["next_page_token"] is None
        assert "expired synthetic transcript" not in response.text
    response = client.post(reply_route, headers={"Idempotency-Key": KEY})
    assert response.status_code == 503
    assert "expired synthetic transcript" not in response.text
    assert store._idempotency_response_bytes == 0


@pytest.mark.parametrize("removal", ["purge", "evict"])
def test_lifecycle_removal_immediately_discards_associated_replay_bytes(desk, removal):
    _client, store, now, _counts = desk
    record = row(store)
    if removal == "purge":
        now[0] += timedelta(seconds=3595)
    cache(store, record)
    assert store._idempotency_response_bytes > 0
    if removal == "purge":
        now[0] += timedelta(seconds=5)
        assert store.purge_expired() == [record["id"]]
    else:
        row(store, "second synthetic row")
        row(store, "third synthetic row")
    assert store._idempotency_response_bytes == 0
    assert (
        store.lookup_idempotency(hash_token(KEY.encode()), ROUTE, hash_token(b"\0"))
        == "unavailable"
    )


def test_replay_denials_and_early_body_errors_are_counted_once(desk):
    client, store, _now, counts = desk
    store.remember_idempotency(
        hash_token(KEY.encode()),
        ROUTE,
        hash_token(b"\0"),
        503,
        b'{"detail":"synthetic unavailable"}',
    )
    for _ in range(2):
        response = client.post(ROUTE, headers={"Idempotency-Key": KEY})
        assert response.status_code == 503
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert response.headers["Content-Security-Policy"]
    assert counts.snapshot() == {"4xx": 0, "5xx": 2}
    oversized = client.post(
        "/api/ingest",
        content=b"x" * (MAX_IDEMPOTENCY_REQUEST_BYTES + 1),
        headers={"Idempotency-Key": "synthetic-oversize-key"},
    )
    assert oversized.status_code == 413
    assert counts.snapshot() == {"4xx": 1, "5xx": 2}


def test_replay_cannot_serve_old_success_when_server_key_is_removed(desk, monkeypatch):
    client, store, _now, _counts = desk
    cache(store, row(store))
    assert client.post(ROUTE, headers={"Idempotency-Key": KEY}).status_code == 200
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    clear_settings_cache()
    response = client.post(ROUTE, headers={"Idempotency-Key": KEY})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "missing_api_key"
    assert "audio_base64" not in response.text
