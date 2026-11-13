"""Dispatcher lifecycle, SOS escalation, audit, and usage (issue 25)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from rasta.main import app
from rasta.settings import clear_settings_cache
from rasta.store import (
    EventNotFound,
    EventStore,
    IllegalTransition,
    VersionConflict,
    attach_event_store,
)

PASSCODE = "desk-workflow-passphrase-25"
HEADERS = {"X-Dispatch-Passcode": PASSCODE}


def _accident(n: int = 0) -> dict:
    return {
        "transcript": f"help line {n} 9876543210 secret-should-not-be-audited",
        "event": {
            "intent": "accident_sos",
            "order_id": "18",
            "eta_minutes": None,
            "urgency": "high",
            "dispatch_action": "stay safe and contact dispatch",
            "transcript": f"help line {n}",
            "confidence": 0.8,
        },
    }


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    monkeypatch.setenv("DISPATCH_PASSCODE", PASSCODE)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    monkeypatch.setenv("SOS_ACK_SECONDS", "60")
    monkeypatch.setenv("RASTA_DB_PATH", str(tmp_path / "desk.sqlite"))
    clear_settings_cache()
    with TestClient(app) as client:
        yield client
    clear_settings_cache()


def test_append_stamps_new_envelope_and_rider_header(client: TestClient):
    store = attach_event_store(app)
    record = store.append(_accident(1))
    assert record["state"] == "new"
    assert record["version"] == 1
    assert record["rider_id"].startswith("r_")
    assert record["event"]["intent"] == "accident_sos"
    # Frozen event is untouched besides the provided fields.
    assert record["ack_by"] is None

    token = client.post(
        "/api/ingest",
        # No real audio path here: stamp is unit-tested on the store; HTTP
        # header coverage uses the sample route's header plumbing via store bind.
        headers={"X-Rider-Id": "r_custom_token_1"},
    )
    # 400/413/503 are fine; header binding is tested directly below.
    assert token.status_code != 500
    from rasta.store import bind_rider_header, reset_rider_header

    bound = bind_rider_header("r_custom_token_1")
    try:
        stamped = store.append(_accident(2))
        assert stamped["rider_id"] == "r_custom_token_1"
    finally:
        reset_rider_header(bound)


def test_ack_resolve_escalate_and_illegal_transitions(client: TestClient):
    store = attach_event_store(app)
    row = store.append(_accident(3))
    event_id = row["id"]

    denied = client.post(f"/api/events/{event_id}/ack", headers={"If-Match": '"1"'})
    assert denied.status_code == 401

    missing = client.post(
        f"/api/events/{event_id}/ack",
        headers={**HEADERS},
        json={"actor": "d_anju"},
    )
    assert missing.status_code == 428

    ack = client.post(
        f"/api/events/{event_id}/ack",
        headers={**HEADERS, "If-Match": '"1"'},
        json={"actor": "d_anju"},
    )
    assert ack.status_code == 200
    body = ack.json()
    assert body["state"] == "acked"
    assert body["version"] == 2
    assert body["ack_by"] == "d_anju"
    assert body["event"]["intent"] == "accident_sos"

    stale = client.post(
        f"/api/events/{event_id}/resolve",
        headers={**HEADERS, "If-Match": '"1"'},
        json={"actor": "d_anju"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    again = client.post(
        f"/api/events/{event_id}/ack",
        headers={**HEADERS, "If-Match": '"2"'},
        json={"actor": "d_anju"},
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "illegal_transition"

    resolved = client.post(
        f"/api/events/{event_id}/resolve",
        headers={**HEADERS, "If-Match": '"2"'},
        json={"actor": "d_anju"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "resolved"
    assert resolved.json()["version"] == 3


def test_resolve_from_escalated_requires_ack(client: TestClient):
    store = attach_event_store(app)
    row = store.append(_accident(4))
    escalated = client.post(
        f"/api/events/{row['id']}/escalate",
        headers={**HEADERS, "If-Match": '"1"'},
        json={"actor": "d_anju"},
    )
    assert escalated.status_code == 200
    assert escalated.json()["state"] == "escalated"

    blocked = client.post(
        f"/api/events/{row['id']}/resolve",
        headers={**HEADERS, "If-Match": '"2"'},
        json={"actor": "d_anju"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "illegal_transition"

    resolved = client.post(
        f"/api/events/{row['id']}/resolve",
        headers={**HEADERS, "If-Match": '"2"'},
        json={"actor": "d_anju", "ack": True},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["state"] == "resolved"
    assert body["ack_by"] == "d_anju"


def test_auto_escalate_unacked_sos_and_audit_shape(monkeypatch, tmp_path):
    clock = {"now": datetime(2026, 11, 13, 12, 0, tzinfo=UTC)}

    def now() -> datetime:
        return clock["now"]

    path = str(tmp_path / "desk.sqlite")
    store = EventStore(capacity=10, path=path, clock=now)
    try:
        row = store.append(_accident(5))
        assert store.escalate_overdue(60) == 0
        clock["now"] = clock["now"] + timedelta(seconds=61)
        assert store.escalate_overdue(60) == 1
        updated = store.get(row["id"])
        assert updated is not None
        assert updated["state"] == "escalated"
        assert updated["version"] == 2
        audit = store.list_audit(row["id"])
        assert [item["action"] for item in audit] == ["ingest", "escalate"]
        blob = str(audit)
        assert "9876543210" not in blob
        assert "secret-should-not-be-audited" not in blob
        assert PASSCODE not in blob
        assert "test-key" not in blob
        assert "GNANI_API_KEY" not in blob
    finally:
        store.close()


def test_list_with_zero_ttl_escalates_and_usage_is_passcode_protected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SOS_ACK_SECONDS", "0")
    clear_settings_cache()
    store = attach_event_store(app, replace=True)
    row = store.append(_accident(6))
    denied = client.get("/api/admin/usage")
    assert denied.status_code in {401, 503}
    listed = client.get("/api/events", headers=HEADERS)
    assert listed.status_code == 200
    events = listed.json()["events"]
    match = next(item for item in events if item["id"] == row["id"])
    assert match["state"] == "escalated"
    usage = client.get("/api/admin/usage", headers=HEADERS)
    assert usage.status_code == 200
    body = usage.json()
    assert body["events"]["escalated"] >= 1
    assert body["sos_unacked"] >= 1
    assert "demo_credits_remaining" in body
    assert "gnani_calls" in body
    dumped = usage.text
    assert PASSCODE not in dumped
    assert "test-key" not in dumped


def test_direct_illegal_and_stale_match_raise():
    store = EventStore(capacity=5, path=":memory:")
    try:
        row = store.append(_accident(7))
        with pytest.raises(VersionConflict):
            store.transition(row["id"], action="ack", actor="d_anju", if_match=9)
        store.transition(row["id"], action="ack", actor="d_anju", if_match=1)
        with pytest.raises(IllegalTransition):
            store.transition(row["id"], action="ack", actor="d_anju", if_match=2)
        with pytest.raises(EventNotFound):
            store.transition("missing-id", action="ack", actor="d_anju", if_match=1)
    finally:
        store.close()
