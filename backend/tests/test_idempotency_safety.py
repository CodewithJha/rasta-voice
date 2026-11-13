"""Concurrency, bounded buffering, privacy and response-policy replay regressions."""

import asyncio
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.errors import ContractApp
from rasta.idempotency import (
    MAX_IDEMPOTENCY_REQUEST_BYTES,
    IdempotencyBodyTooLarge,
    IdempotencyMiddleware,
    _buffer_body,
)
from rasta.main import app
from rasta.security import SECURITY_HEADERS
from rasta.settings import clear_settings_cache
from rasta.store import EventStore, attach_event_store


def test_concurrent_identical_work_claims_once_before_gnani(monkeypatch, make_wav):
    monkeypatch.setenv("GNANI_API_KEY", "test-only-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    clear_settings_cache()
    entered, release = threading.Event(), threading.Event()
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path == "/api/v1/tts/inference":
            entered.set()
            assert release.wait(5)
            return httpx.Response(200, content=make_wav(seconds=0.2, rate=16000))
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "synthetic-claim-request",
                "transcript": "customer phone nahi utha raha, order 18",
                "model": "prisma-v3.0",
                "detected_language_code": "hi-IN",
                "processing_time": 0.1,
            },
        )

    transport = httpx.MockTransport(handler)
    for cls in (PrismaSTT, TimbreTTS):
        monkeypatch.setattr(
            cls, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
        )
    headers = {"Idempotency-Key": "concurrent-key-fixture"}
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, "/api/ingest/sample?condition=clean", headers=headers)
        try:
            assert entered.wait(3)
            duplicate = client.post("/api/v1/ingest/sample?condition=clean", headers=headers)
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "idempotency_in_progress"
            conflict = client.post("/api/ingest/sample?condition=noisy", headers=headers)
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "idempotency_conflict"
            assert len(seen) == 1
        finally:
            release.set()
        original = first.result(timeout=5)
        assert original.status_code == 200
        replay = client.post("/api/ingest/sample?condition=clean", headers=headers)
        assert replay.status_code == 200
        assert replay.json() == original.json()
        assert len(seen) == 2  # One Timbre plus one Prisma, never two of each.


def test_replayed_errors_and_all_denials_keep_current_id_and_policy(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    clear_settings_cache()
    with TestClient(app, base_url="https://testserver") as client:
        responses = []
        for _ in range(2):
            rid = str(uuid4())
            response = client.post(
                "/api/ingest/sample",
                headers={"Idempotency-Key": "missing-key-fixture", "X-Request-ID": rid},
            )
            assert response.status_code == 503
            assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"] == rid
            responses.append(response)
        responses.append(client.post("/api/ingest/sample", headers={"Idempotency-Key": "bad"}))
        responses.append(
            client.post(
                "/api/ingest/sample?condition=noisy",
                headers={"Idempotency-Key": "missing-key-fixture"},
            )
        )
        assert [response.status_code for response in responses] == [503, 503, 400, 409]
        for response in responses:
            for name, value in SECURITY_HEADERS.items():
                assert response.headers[name] == value
            assert response.headers["Strict-Transport-Security"]
            assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("length", [None, "1"])
def test_keyed_body_is_bounded_before_handler_even_with_understated_length(length):
    probe = ContractApp()
    called = []

    @probe.post("/api/ingest")
    async def ingest(request: Request):
        called.append(1)
        return {"size": len(await request.body())}

    headers = {"Idempotency-Key": "bounded-body-fixture"}
    if length is not None:
        headers["Content-Length"] = length
    with TestClient(probe) as client:
        response = client.post(
            "/api/ingest",
            content=iter([b"x" * MAX_IDEMPOTENCY_REQUEST_BYTES, b"x"]),
            headers=headers,
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"
        assert response.headers["Content-Security-Policy"]
        assert not called


def test_buffer_stops_on_overflow_and_disconnect():
    async def run():
        messages = [
            {
                "type": "http.request",
                "body": b"a" * MAX_IDEMPOTENCY_REQUEST_BYTES,
                "more_body": True,
            },
            {"type": "http.request", "body": b"b", "more_body": True},
            {"type": "http.request", "body": b"must-not-be-read"},
        ]

        async def receive():
            return messages.pop(0)

        with pytest.raises(IdempotencyBodyTooLarge):
            await _buffer_body(receive)
        assert len(messages) == 1
        messages[:] = [{"type": "http.disconnect"}]
        with pytest.raises(ClientDisconnect):
            await _buffer_body(receive)

    asyncio.run(run())


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_interrupted_outcome_cannot_start_paid_work_again(failure):
    probe = ContractApp()
    calls = []

    async def interrupted(scope, receive, send):
        calls.append(1)
        raise failure()

    middleware = IdempotencyMiddleware(interrupted)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/ingest/sample",
        "headers": [(b"idempotency-key", b"uncertain-key-fixture")],
        "app": probe,
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    store = attach_event_store(probe)
    try:
        with pytest.raises(failure):
            asyncio.run(middleware(scope, receive, send))
        asyncio.run(middleware(scope, receive, send))
        assert calls == [1]
        assert messages[0]["status"] == 503
        assert json.loads(messages[-1]["body"])["error"]["code"] == "idempotency_outcome_unknown"
        assert middleware._pending == {}
    finally:
        store.close()


def test_sqlite_retains_only_metadata_and_restart_never_repeats_audio(tmp_path):
    path = str(tmp_path / "replay.sqlite")
    store = EventStore(10, path)
    audio = base64.b64encode(b"test-only in-memory audio marker").decode()
    response = json.dumps({"transcript": "test-only transcript", "audio_base64": audio}).encode()
    store.remember_idempotency("key-hash", "/api/simulate", "body-hash", 200, response)
    assert store.lookup_idempotency("key-hash", "/api/simulate", "body-hash") == (200, response)
    persisted = store._conn.execute("SELECT route, response FROM idempotency").fetchone()
    assert persisted[0] != "/api/simulate"
    assert len(persisted[0]) == 64
    assert persisted[1] == ""
    store.close()
    assert audio.encode() not in (tmp_path / "replay.sqlite").read_bytes()
    restarted = EventStore(10, path)
    try:
        assert (
            restarted.lookup_idempotency("key-hash", "/api/simulate", "body-hash") == "unavailable"
        )
        assert restarted.lookup_idempotency("key-hash", "/api/simulate", "changed") == "conflict"
    finally:
        restarted.close()


def test_memory_eviction_and_deleted_event_cannot_reveal_or_repeat_work(monkeypatch):
    monkeypatch.setattr("rasta.store.IDEMPOTENCY_RESPONSE_ENTRIES", 1)
    now = [datetime(2026, 11, 14, tzinfo=UTC)]
    store = EventStore(10, ":memory:", clock=lambda: now[0])
    try:
        store.remember_idempotency("first", "/api/simulate", "body", 200, b'{"ok":1}')
        store.remember_idempotency("second", "/api/simulate", "body", 200, b'{"ok":2}')
        assert store.lookup_idempotency("first", "/api/simulate", "body") == "unavailable"
        row = store.append({"transcript": "synthetic event", "event": {"intent": "other"}})
        response = json.dumps({"ingest": row, "audio_base64": "test-only"}).encode()
        store.remember_idempotency("third", "/api/simulate", "body", 200, response)
        assert store.lookup_idempotency("third", "/api/simulate", "body") == (200, response)
        store._conn.execute("DELETE FROM events WHERE id = ?", (row["id"],))
        store._conn.commit()
        assert store.lookup_idempotency("third", "/api/simulate", "body") == "unavailable"
        assert store._idempotency_response_bytes == 0
        now[0] += timedelta(seconds=601)
        assert store.lookup_idempotency("third", "/api/simulate", "body") is None
    finally:
        store.close()


def test_response_byte_budget_discards_payload_but_retains_no_repeat_metadata(monkeypatch):
    monkeypatch.setattr("rasta.store.IDEMPOTENCY_RESPONSE_BYTES", 8)
    store = EventStore(10, ":memory:")
    try:
        store.remember_idempotency(
            "large", "/api/simulate", "body", 200, b'{"payload":"too large"}'
        )
        assert store.lookup_idempotency("large", "/api/simulate", "body") == "unavailable"
        assert store._idempotency_response_bytes == 0
        assert store._conn.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0] == 1
    finally:
        store.close()


def test_failed_persistence_retains_the_claim_to_prevent_double_work(monkeypatch):
    probe = ContractApp()
    store = attach_event_store(probe)
    called = []

    async def completed(scope, receive, send):
        called.append(1)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    def cannot_record(*args):
        raise RuntimeError("synthetic persistence failure")

    monkeypatch.setattr(store, "remember_idempotency", cannot_record)
    middleware = IdempotencyMiddleware(completed)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/ingest/sample",
        "headers": [(b"idempotency-key", b"storage-failure-key")],
        "app": probe,
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    try:
        with pytest.raises(RuntimeError, match="persistence"):
            asyncio.run(middleware(scope, receive, send))
        assert middleware._pending
        asyncio.run(middleware(scope, receive, send))
        assert called == [1]
        assert messages[0]["status"] == 409
        assert json.loads(messages[-1]["body"])["error"]["code"] == "idempotency_in_progress"
    finally:
        store.close()


def test_missing_event_error_replays_without_requiring_a_live_event():
    store = EventStore(10, ":memory:")
    try:
        payload = b'{"detail":"Event not found."}'
        store.remember_idempotency("missing", "/api/reply/absent", "body", 404, payload)
        assert store.lookup_idempotency("missing", "/api/reply/absent", "body") == (404, payload)
    finally:
        store.close()
    assert store._idempotency_responses == {}
    assert store._idempotency_response_bytes == 0
