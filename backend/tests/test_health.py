"""Liveness and readiness probes (issue 22). No network, no live keys."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from rasta.main import app
from rasta.settings import clear_settings_cache, get_settings
from rasta.store import attach_event_store


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    monkeypatch.setenv("DISPATCH_PASSCODE", "synthetic-desk-passcode")
    clear_settings_cache()
    with TestClient(app) as client:
        yield client


def test_health_shape_is_unchanged(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "gnani_key_set": True,
        "llm_provider": "rules",
    }


def test_health_does_not_touch_the_store_or_a_budget(client: TestClient, monkeypatch):
    def fail_store(*_args, **_kwargs):
        raise AssertionError("health must not touch the event store")

    def fail_db():
        raise AssertionError("health must not probe the durable store")

    def fail_limiter(_app):
        raise AssertionError("health must not read the speech budget")

    monkeypatch.setattr("rasta.store.attach_event_store", fail_store)
    monkeypatch.setattr("rasta.readiness.check_db_writable", fail_db)
    monkeypatch.setattr("rasta.readiness.limiter_fields", fail_limiter)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_ready_reads_issue_13_budget_and_marks_later_issues(client: TestClient):
    attach_event_store(app, replace=True)
    settings = get_settings()
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["gnani_key_set"] is True
    assert body["db_writable"] == "not_deployed"
    assert body["rate_limit"] == {
        "ok": True,
        "per_ip_requests_per_minute": settings.per_ip_requests_per_minute,
    }
    assert body["demo_credits_remaining"] == settings.demo_speech_budget
    assert body["demo_credits_exhausted"] is False
    assert body["schema_version"] == "not_deployed"
    assert body["circuit_breaker"] == "not_deployed"
    assert body["events_in_store"] == 0


def test_ready_counts_in_memory_events(client: TestClient):
    attach_event_store(app, replace=True).append({"event": {"intent": "other"}})
    body = client.get("/api/ready").json()
    assert body["events_in_store"] == 1
    assert client.get("/api/health").json()["ok"] is True


def test_ready_503_when_configured_store_is_not_writable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("rasta.readiness.check_db_writable", lambda: False)
    response = client.get("/api/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["db_writable"] is False
    # Still liveness-healthy: a tight restart loop must not flap on disk.
    assert client.get("/api/health").status_code == 200


def test_ready_200_when_budget_is_exhausted(client: TestClient):
    class Guard:
        def remaining(self) -> int:
            return 0

    app.state.speech_guard = Guard()
    try:
        response = client.get("/api/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["demo_credits_remaining"] == 0
        assert body["demo_credits_exhausted"] is True
        assert body["rate_limit"]["ok"] is True
    finally:
        from rasta.limits import attach_speech_guard

        attach_speech_guard(app, replace=True)


def test_ready_reads_a_remaining_budget(client: TestClient):
    class Guard:
        def remaining(self) -> int:
            return 17

    app.state.speech_guard = Guard()
    try:
        body = client.get("/api/ready").json()
        assert body["demo_credits_remaining"] == 17
        assert body["demo_credits_exhausted"] is False
        assert body["rate_limit"] == {
            "ok": True,
            "per_ip_requests_per_minute": get_settings().per_ip_requests_per_minute,
        }
    finally:
        from rasta.limits import attach_speech_guard

        attach_speech_guard(app, replace=True)


def test_payloads_never_include_secrets(client: TestClient):
    health = json.dumps(client.get("/api/health").json())
    ready = json.dumps(client.get("/api/ready").json())
    for payload in (health, ready):
        assert "synthetic-desk-passcode" not in payload
        assert "test-key" not in payload
        assert "GNANI_API_KEY" not in payload
        assert "DISPATCH_PASSCODE" not in payload


def test_db_probe_returns_not_deployed_without_a_path(monkeypatch: pytest.MonkeyPatch):
    from rasta.readiness import check_db_writable

    monkeypatch.setattr("rasta.readiness.configured_db_path", lambda: None)
    assert check_db_writable() == "not_deployed"


def test_db_probe_false_on_sqlite_error(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from rasta.readiness import check_db_writable

    blocked = tmp_path / "missing-dir" / "events.db"

    def boom(_path):
        raise OSError("read-only volume")

    monkeypatch.setattr("rasta.readiness.configured_db_path", lambda: blocked)
    monkeypatch.setattr("rasta.readiness.sqlite3.connect", boom)
    assert check_db_writable() is False


def test_db_probe_true_on_writable_sqlite(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from rasta.readiness import check_db_writable

    path = tmp_path / "events.db"
    monkeypatch.setattr("rasta.readiness.configured_db_path", lambda: path)
    assert check_db_writable() is True
    # Probe is a no-op write: the file may exist after connect, but no schema.
