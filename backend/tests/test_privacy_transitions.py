"""Regression for expired or legacy transcripts escaping through dispatcher writes."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from rasta.main import app
from rasta.settings import clear_settings_cache
from rasta.store import EventNotFound, EventStore

SECRET = "synthetic-ttl-desk-fixture"
PHONE = "9876543210"


def payload():
    return {
        "transcript": "synthetic private text",
        "event": {
            "intent": "accident_sos",
            "order_id": "18",
            "eta_minutes": None,
            "urgency": "high",
            "dispatch_action": "contact dispatch",
            "transcript": "synthetic private text",
            "confidence": 0.5,
        },
    }


@pytest.mark.parametrize("action", ["ack", "resolve", "escalate"])
@pytest.mark.parametrize("version", [1, 999])
def test_expired_writes_return_404_before_version_or_state_checks(monkeypatch, action, version):
    monkeypatch.setenv("DISPATCH_PASSCODE", SECRET)
    clear_settings_cache()
    now = [datetime(2026, 11, 14, tzinfo=UTC)]
    store = EventStore(10, ":memory:", clock=lambda: now[0], ttl_hours=1)
    row = store.append(payload())
    audit_before = store.list_audit(row["id"])
    monkeypatch.setattr(app.state, "event_store", store, raising=False)
    client = TestClient(app)  # No lifespan replacement of the patched-clock store.
    try:
        now[0] += timedelta(hours=1)
        assert store.get(row["id"]) is None
        assert store.list_since(None) == []
        response = client.post(
            f"/api/events/{row['id']}/{action}",
            json={"ack": True},
            headers={"X-Dispatch-Passcode": SECRET, "If-Match": f'"{version}"'},
        )
        assert response.status_code == 404
        assert "synthetic private text" not in response.text
        assert store.list_audit(row["id"]) == audit_before
        with pytest.raises(EventNotFound):
            store.transition(row["id"], action=action, actor="d_fixture", if_match=version)
    finally:
        client.close()
        store.close()
        clear_settings_cache()


def test_transition_redacts_legacy_row_and_preserves_live_boundary(monkeypatch):
    monkeypatch.setenv("DISPATCH_PASSCODE", SECRET)
    clear_settings_cache()
    now = [datetime(2026, 11, 14, tzinfo=UTC)]
    store = EventStore(10, ":memory:", clock=lambda: now[0], ttl_hours=1)
    row = store.append(payload())
    legacy = {**row, "transcript": PHONE, "event": {**row["event"], "transcript": PHONE}}
    store._conn.execute(
        "UPDATE events SET payload = ? WHERE id = ?", (json.dumps(legacy), row["id"])
    )
    store._conn.commit()
    monkeypatch.setattr(app.state, "event_store", store, raising=False)
    client = TestClient(app)
    try:
        now[0] += timedelta(seconds=3599)
        response = client.post(
            f"/api/events/{row['id']}/ack",
            json={},
            headers={"X-Dispatch-Passcode": SECRET, "If-Match": '"1"'},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "acked"
        assert PHONE not in response.text
        assert response.json()["transcript"] == "[redacted]"
        stored = store._conn.execute(
            "SELECT payload FROM events WHERE id = ?", (row["id"],)
        ).fetchone()[0]
        assert PHONE not in stored
        now[0] += timedelta(seconds=1)
        with pytest.raises(EventNotFound):
            store.transition(row["id"], action="resolve", actor="d_fixture", if_match=2)
    finally:
        client.close()
        store.close()
        clear_settings_cache()
