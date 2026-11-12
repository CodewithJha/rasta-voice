"""Event store and GET /api/events.

HTTP tests swap the Gnani transport with ``httpx.MockTransport`` the same
way ``test_ingest.py`` does. There is no mock path in app code.
"""

from __future__ import annotations

import threading
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.settings import (
    DEFAULT_EVENT_STORE_CAPACITY,
    MAX_EVENT_STORE_CAPACITY,
    SettingsError,
    clear_settings_cache,
    get_settings,
)
from rasta.store import (
    EventStore,
    InvalidSince,
    attach_event_store,
    parse_since,
)

LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)


def _payload(n: int = 0, **extra) -> dict:
    body = {
        "transcript": f"line {n}",
        "stt": {"model": "prisma-v3.0", "request_id": f"req-{n}"},
        "event": {"intent": "other", "order_id": str(n)},
    }
    body.update(extra)
    return body


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()


# --- settings ---


def test_capacity_default_is_the_issue_cap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EVENT_STORE_CAPACITY", raising=False)
    clear_settings_cache()
    assert get_settings().event_store_capacity == DEFAULT_EVENT_STORE_CAPACITY
    assert DEFAULT_EVENT_STORE_CAPACITY == 200


def test_capacity_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EVENT_STORE_CAPACITY", "50")
    clear_settings_cache()
    assert get_settings().event_store_capacity == 50


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "200.5", "inf", "10001"])
def test_capacity_rejects_invalid(monkeypatch: pytest.MonkeyPatch, raw: str):
    monkeypatch.setenv("EVENT_STORE_CAPACITY", raw)
    clear_settings_cache()
    with pytest.raises(SettingsError, match="EVENT_STORE_CAPACITY"):
        get_settings()


def test_capacity_ceiling_is_documented():
    assert MAX_EVENT_STORE_CAPACITY == 10_000


# --- direct store ---


def test_append_order_is_oldest_first():
    store = EventStore(capacity=10)
    first = store.append(_payload(1))
    second = store.append(_payload(2))
    events = store.list_since(None)
    assert [event["id"] for event in events] == [first["id"], second["id"]]
    assert [event["event"]["order_id"] for event in events] == ["1", "2"]
    assert events[0]["created_at"] < events[1]["created_at"]


def test_201st_append_drops_the_oldest():
    store = EventStore(capacity=200)
    first = store.append(_payload(0))
    for n in range(1, 200):
        store.append(_payload(n))
    assert len(store.list_since(None)) == 200
    newest = store.append(_payload(200))
    events = store.list_since(None)
    assert len(events) == 200
    ids = [event["id"] for event in events]
    assert first["id"] not in ids
    assert newest["id"] == ids[-1]
    assert events[0]["event"]["order_id"] == "1"


def test_smaller_injected_capacity_also_drops_oldest():
    store = EventStore(capacity=3)
    store.append(_payload(1))
    store.append(_payload(2))
    store.append(_payload(3))
    store.append(_payload(4))
    assert [event["event"]["order_id"] for event in store.list_since(None)] == [
        "2",
        "3",
        "4",
    ]


def test_list_since_omitted_or_empty_returns_all():
    store = EventStore(capacity=10)
    store.append(_payload(1))
    store.append(_payload(2))
    assert len(store.list_since(None)) == 2
    assert len(store.list_since("")) == 2
    assert len(store.list_since("   ")) == 2


def test_list_since_is_strictly_after_the_boundary():
    store = EventStore(capacity=10)
    first = store.append(_payload(1))
    second = store.append(_payload(2))
    at_first = store.list_since(first["created_at"])
    assert [event["id"] for event in at_first] == [second["id"]]
    assert store.list_since(second["created_at"]) == []


def test_list_since_rejects_malformed_and_naive():
    store = EventStore(capacity=10)
    store.append(_payload(1))
    with pytest.raises(InvalidSince):
        store.list_since("not-a-timestamp")
    with pytest.raises(InvalidSince):
        store.list_since("2026-11-13T10:00:00")


def test_list_since_accepts_z_suffix_as_utc():
    store = EventStore(capacity=10)
    event = store.append(_payload(1))
    stamp = event["created_at"]
    assert stamp.endswith("+00:00")
    as_z = stamp.removesuffix("+00:00") + "Z"
    assert store.list_since(as_z) == []


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-13T10:00:00+00:00",
        "2026-11-13T10:00:00Z",
        "2026-11-13T10:00:00z",
        "2026-11-13 10:00:00+00:00",
        "0001-01-01T00:00:00+00:00",
        "9999-12-31T23:59:59+00:00",
    ],
)
def test_parse_since_accepts_aware_instants(value: str):
    parsed = parse_since(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "value",
    [
        "0001-01-01T00:00:00+01:00",  # fromisoformat ok; astimezone overflows
        "9999-12-31T23:59:59-01:00",
        "not-a-timestamp",
        "yesterday",
        "2026-11-13T10:00:00",  # naive
        "2026-11-13",  # date-only, naive
        "2026-11-13Z",  # date-only even with Z stays naive in Python
        "2026-11-13T10:00:00+24:00",
        "2026-11-13T10:00:00+99:00",
        "2026-11-13T10:00:00-24:00",
        "2026-13-01T00:00:00+00:00",
        "2026-11-13T10:00:00+00:00 extra",
        "",
        "2026-11-13T10:00:00+00:00" + "0" * 80,  # over the length cap
        123,
        None,
        b"2026-11-13T10:00:00+00:00",
    ],
)
def test_parse_since_rejects_unusable_values(value):
    with pytest.raises(InvalidSince):
        parse_since(value)


def test_append_keeps_the_full_payload():
    # PR #37 adds envelope fields such as extractor_source. The store must
    # copy the ingest dict as-is, not a hand-picked key list.
    store = EventStore(capacity=10)
    payload = _payload(
        1, extractor_source="rules", fallback_reason="missing_api_key"
    )
    out = store.append(payload)
    assert out["extractor_source"] == "rules"
    assert out["fallback_reason"] == "missing_api_key"
    listed = store.list_since(None)[0]
    assert listed["extractor_source"] == "rules"
    assert listed["fallback_reason"] == "missing_api_key"


def test_copy_isolation():
    store = EventStore(capacity=10)
    payload = _payload(1)
    out = store.append(payload)
    payload["transcript"] = "mutated input"
    payload["event"]["intent"] = "delay"
    out["transcript"] = "mutated return"
    out["event"]["intent"] = "accident_sos"
    out["id"] = "not-the-stored-id"
    held = store.list_since(None)[0]
    assert held["transcript"] == "line 1"
    assert held["event"]["intent"] == "other"
    assert held["id"] != "not-the-stored-id"
    listed = store.list_since(None)
    listed[0]["event"]["intent"] = "item_missing"
    assert store.list_since(None)[0]["event"]["intent"] == "other"


def test_created_at_is_strictly_monotonic_when_the_clock_stalls():
    frozen = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)

    def clock() -> datetime:
        return frozen

    store = EventStore(capacity=10, clock=clock)
    first = store.append(_payload(1))
    second = store.append(_payload(2))
    assert first["created_at"] == "2026-11-13T10:00:00+00:00"
    assert second["created_at"] == "2026-11-13T10:00:00.000001+00:00"
    assert store.list_since(first["created_at"])[0]["id"] == second["id"]


def test_concurrent_appends_keep_every_record():
    store = EventStore(capacity=200)
    n_threads = 8
    per_thread = 20
    barrier = threading.Barrier(n_threads)

    def worker(offset: int) -> None:
        barrier.wait()
        for n in range(per_thread):
            store.append(_payload(offset + n))

    threads = [
        threading.Thread(target=worker, args=(i * per_thread,)) for i in range(n_threads)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    events = store.list_since(None)
    assert len(events) == n_threads * per_thread
    ids = [event["id"] for event in events]
    assert len(set(ids)) == len(ids)
    stamps = [datetime.fromisoformat(event["created_at"]) for event in events]
    assert all(earlier < later for earlier, later in zip(stamps, stamps[1:]))
    assert all(stamp.tzinfo is not None for stamp in stamps)


# --- HTTP ---


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, make_wav) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/tts/inference":
            return httpx.Response(200, content=make_wav(seconds=1.0, rate=16000))
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

    transport = httpx.MockTransport(handler)
    for cls in (PrismaSTT, TimbreTTS):
        monkeypatch.setattr(
            cls, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
        )
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    return seen


@pytest.fixture
def client(calls) -> TestClient:
    # Lifespan installs a fresh store so HTTP tests do not share a desk.
    with TestClient(app) as test_client:
        yield test_client


def _upload(client: TestClient, make_wav, name: str = "clip.wav"):
    return client.post(
        "/api/ingest",
        files={"audio_file": (name, make_wav(seconds=2.0), "audio/wav")},
    )


def test_two_ingests_are_stored_oldest_first(client: TestClient, make_wav):
    first = _upload(client, make_wav)
    second = _upload(client, make_wav)
    assert first.status_code == 200
    assert second.status_code == 200
    for body in (first.json(), second.json()):
        assert body["id"]
        stamp = datetime.fromisoformat(body["created_at"])
        assert stamp.tzinfo is not None
        assert stamp.utcoffset() == timedelta(0)
        assert body["transcript"]
        assert body["stt"]["model"] == "prisma-v3.0"
        assert body["event"]["intent"] == "customer_unreachable"
        assert "sample_text" not in body

    listed = client.get("/api/events")
    assert listed.status_code == 200
    events = listed.json()["events"]
    assert [event["id"] for event in events] == [first.json()["id"], second.json()["id"]]
    assert events[0]["created_at"] < events[1]["created_at"]
    assert events[0]["event"]["order_id"] == "18"
    # Full ingest envelope is stored as-is, including extractor fields from #37.
    assert first.json()["extractor_source"] == events[0]["extractor_source"]
    assert "fallback_reason" in first.json() and "fallback_reason" in events[0]


def test_sample_ingest_shares_id_but_does_not_store_sample_text(
    client: TestClient,
):
    response = client.post("/api/ingest/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["sample_text"]
    events = client.get("/api/events").json()["events"]
    assert len(events) == 1
    assert events[0]["id"] == body["id"]
    assert events[0]["created_at"] == body["created_at"]
    assert "sample_text" not in events[0]


def test_events_since_returns_only_newer(client: TestClient, make_wav):
    first = _upload(client, make_wav).json()
    second = _upload(client, make_wav).json()
    later = client.get("/api/events", params={"since": first["created_at"]})
    assert later.status_code == 200
    events = later.json()["events"]
    assert [event["id"] for event in events] == [second["id"]]
    empty = client.get("/api/events", params={"since": second["created_at"]})
    assert empty.json() == {"events": []}


@pytest.mark.parametrize(
    "since",
    [
        "not-a-timestamp",
        "2026-11-13T10:00:00",
        "yesterday",
        "2026-11-13",
        "2026-11-13T10:00:00+24:00",
        "0001-01-01T00:00:00+01:00",
        "9999-12-31T23:59:59-01:00",
        "2026-11-13T10:00:00+00:00" + "0" * 80,
    ],
)
def test_events_since_invalid_is_422(client: TestClient, since: str):
    # raise_server_exceptions stays on: a leaked OverflowError would fail the test.
    response = client.get("/api/events", params={"since": since})
    assert response.status_code == 422
    assert "timezone-aware" in response.json()["detail"] or "ISO 8601" in str(
        response.json()["detail"]
    )


def test_events_since_range_overflow_is_422_not_500():
    """Normalization overflow must not become an unhandled 500."""
    with TestClient(app, raise_server_exceptions=False) as client:
        for since in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            response = client.get("/api/events", params={"since": since})
            assert response.status_code == 422, since


def test_concurrent_http_ingests_are_stored_with_unique_ids(client: TestClient, make_wav):
    """Ingest runs in worker threads (asyncio.to_thread). The store must stay consistent."""
    n = 8
    barrier = threading.Barrier(n)
    responses: list = [None] * n

    def worker(index: int) -> None:
        barrier.wait()
        responses[index] = _upload(client, make_wav)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(response is not None and response.status_code == 200 for response in responses)
    events = client.get("/api/events").json()["events"]
    assert len(events) == n
    ids = [event["id"] for event in events]
    assert len(set(ids)) == n
    stamps = [datetime.fromisoformat(event["created_at"]) for event in events]
    assert all(earlier < later for earlier, later in zip(stamps, stamps[1:]))
    assert {event["id"] for event in events} == {response.json()["id"] for response in responses}


def test_failed_ingest_is_not_stored(client: TestClient, make_wav):
    empty = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", b"", "audio/wav")},
    )
    assert empty.status_code == 400
    assert client.get("/api/events").json() == {"events": []}

    _upload(client, make_wav)
    assert len(client.get("/api/events").json()["events"]) == 1


def test_upstream_error_is_not_stored(monkeypatch: pytest.MonkeyPatch, make_wav):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402, json={"detail": {"error_code": "INSUFFICIENT_CREDIT", "message": "No credit"}}
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        PrismaSTT, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
    )
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    with TestClient(app) as client:
        attach_event_store(app, replace=True)
        response = client.post(
            "/api/ingest", files={"audio_file": ("clip.wav", make_wav(), "audio/wav")}
        )
        assert response.status_code == 502
        assert client.get("/api/events").json() == {"events": []}


def test_missing_key_is_not_stored(monkeypatch: pytest.MonkeyPatch, make_wav):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with TestClient(app) as client:
        attach_event_store(app, replace=True)
        response = client.post(
            "/api/ingest", files={"audio_file": ("clip.wav", make_wav(), "audio/wav")}
        )
        assert response.status_code == 503
        assert client.get("/api/events").json() == {"events": []}
