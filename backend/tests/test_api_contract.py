"""API contract: error envelope, aliases, idempotency, pagination (issue 26)."""

from contextlib import nullcontext

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.settings import clear_settings_cache
from rasta.store import EventStore, attach_event_store

LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)
PASSCODE = "desk-contract-passphrase-26"
DESK = {"X-Dispatch-Passcode": PASSCODE}


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
    return TestClient(app)


def test_health_alias_matches_unversioned(client: TestClient):
    unversioned = client.get("/api/health")
    aliased = client.get("/api/v1/health")
    assert unversioned.status_code == 200
    assert aliased.status_code == 200
    assert aliased.json() == unversioned.json()


def test_validation_error_uses_the_envelope(client: TestClient):
    response = client.post("/api/ingest/sample", params={"condition": "not-a-mix"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "clean or noisy" in error["message"]
    assert error["request_id"]
    assert response.headers["x-request-id"] == error["request_id"]


def test_missing_key_503_uses_the_envelope(monkeypatch: pytest.MonkeyPatch, make_wav):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    response = TestClient(app).post(
        "/api/ingest", files={"audio_file": ("clip.wav", make_wav(), "audio/wav")}
    )
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "missing_api_key"
    assert "GNANI_API_KEY is not set" in error["message"]
    assert error["request_id"]


def test_gnani_failures_are_mapped(monkeypatch: pytest.MonkeyPatch, make_wav):
    seen: list[int] = []
    current = {"status": 500}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(
            current["status"], json={"detail": {"message": "raw upstream"}}
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        PrismaSTT, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
    )
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")

    cases = [
        (429, 429, "upstream_rate_limited"),
        (402, 503, "upstream_out_of_credit"),
        (500, 502, "upstream_error"),
    ]
    for upstream, http_status, code in cases:
        current["status"] = upstream
        seen.clear()
        response = TestClient(app).post(
            "/api/ingest",
            files={"audio_file": ("clip.wav", make_wav(), "audio/wav")},
        )
        assert response.status_code == http_status, code
        error = response.json()["error"]
        assert error["code"] == code
        assert error["upstream_status"] == upstream
        assert "raw upstream" not in error["message"]
        assert error["request_id"]
        assert seen == [1]


def test_sample_idempotency_replays_without_a_second_gnani_call(client: TestClient, calls):
    headers = {"Idempotency-Key": "sample-key-26"}
    first = client.post("/api/ingest/sample", headers=headers)
    assert first.status_code == 200
    first_body = first.json()
    first_calls = len(calls)
    assert first_calls == 2
    second = client.post("/api/ingest/sample", headers=headers)
    assert second.status_code == 200
    assert second.json() == first_body
    assert len(calls) == first_calls
    ingest = first_body["ingest"]
    assert ingest["id"] == second.json()["ingest"]["id"]
    assert ingest["stt"]["request_id"] == "req-1"


def test_idempotency_conflict_on_a_different_body(client: TestClient, calls):
    headers = {"Idempotency-Key": "same-key-different-condition"}
    first = client.post("/api/ingest/sample", params={"condition": "clean"}, headers=headers)
    assert first.status_code == 200
    conflict = client.post(
        "/api/ingest/sample", params={"condition": "noisy"}, headers=headers
    )
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "idempotency_conflict"
    assert error["request_id"]
    assert len(calls) == 2


def test_event_pagination_returns_a_stable_next_page_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    monkeypatch.setenv("DISPATCH_PASSCODE", PASSCODE)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("RASTA_DB_PATH", str(tmp_path / "desk.sqlite"))
    clear_settings_cache()
    with TestClient(app) as client:
        store = attach_event_store(app)
        assert isinstance(store, EventStore)
        for index in range(3):
            store.append(
                {
                    "transcript": f"line {index}",
                    "event": {
                        "intent": "other",
                        "order_id": str(index),
                        "eta_minutes": None,
                        "urgency": "low",
                        "dispatch_action": "note it",
                        "transcript": f"line {index}",
                        "confidence": 0.7,
                    },
                }
            )
        first = client.get("/api/events", params={"limit": 2}, headers=DESK)
        assert first.status_code == 200
        body = first.json()
        assert "events" in body and "next_page_token" in body
        assert len(body["events"]) == 2
        assert body["next_page_token"]
        second = client.get(
            "/api/events",
            params={"limit": 2, "page_token": body["next_page_token"]},
            headers=DESK,
        )
        assert second.status_code == 200
        page = second.json()
        assert len(page["events"]) == 1
        assert page["next_page_token"] is None
        assert page["events"][0]["id"] not in {row["id"] for row in body["events"]}
    clear_settings_cache()
