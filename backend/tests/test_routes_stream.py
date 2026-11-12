"""WebSocket /api/stream against a fake Prisma connect on app.state."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rasta.main import app
from rasta.pipeline import SAMPLE_LINE
from rasta.settings import clear_settings_cache
from rasta.store import attach_event_store

ORIGIN = {"Origin": "http://localhost:5173"}
FRAME = bytes([1, 0]) * 512  # 1024 bytes of PCM


class FakeSocket:
    def __init__(
        self,
        outgoing: list[str],
        transcripts_on_commit: list[dict[str, Any]],
        refuse: Exception | None = None,
    ) -> None:
        self.sent: list[Any] = []
        self.audio_received = threading.Event()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        for frame in outgoing:
            self._queue.put_nowait(frame)
        self._transcripts = list(transcripts_on_commit)
        self._committed = False

    async def send(self, data: Any) -> None:
        self.sent.append(data)
        if isinstance(data, (bytes, bytearray)):
            self.audio_received.set()
        if _is_commit(data) and not self._committed:
            self._committed = True
            for frame in self._transcripts:
                await self._queue.put(json.dumps(frame))
            await self._queue.put(None)

    def __aiter__(self) -> FakeSocket:
        return self

    async def __anext__(self) -> str:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self) -> None:
        await self._queue.put(None)


class FakeConnect:
    def __init__(
        self,
        *,
        transcripts: list[dict[str, Any]] | None = None,
        refuse: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sockets: list[FakeSocket] = []
        self.transcripts = transcripts or [
            {
                "type": "transcript",
                "text": SAMPLE_LINE,
                "segment_id": "req-live-seg-1",
            }
        ]
        self.refuse = refuse
        self.outgoing = [json.dumps({"type": "connected", "request_id": "req-live"})]

    def __call__(self, url: str, additional_headers: dict[str, str] | None = None, **_: Any):
        self.calls.append({"url": url, "headers": dict(additional_headers or {})})
        socket = FakeSocket(self.outgoing, self.transcripts, self.refuse)
        self.sockets.append(socket)
        return _FakeCM(socket, self.refuse)


class _FakeCM:
    def __init__(self, socket: FakeSocket, refuse: Exception | None) -> None:
        self._socket = socket
        self._refuse = refuse

    async def __aenter__(self) -> FakeSocket:
        if self._refuse is not None:
            raise self._refuse
        return self._socket

    async def __aexit__(self, *exc: object) -> None:
        await self._socket.close()


def _is_commit(data: Any) -> bool:
    if not isinstance(data, str):
        return False
    try:
        frame = json.loads(data)
    except json.JSONDecodeError:
        return False
    return isinstance(frame, dict) and frame.get("type") == "commit"


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    monkeypatch.delenv("RASTA_MAX_STREAMS", raising=False)
    monkeypatch.delenv("RASTA_STREAM_IDLE_SECONDS", raising=False)
    monkeypatch.delenv("RASTA_STREAM_HEARTBEAT_SECONDS", raising=False)
    monkeypatch.delenv("RASTA_STREAM_DRAIN_SECONDS", raising=False)
    monkeypatch.delenv("RASTA_STREAM_SESSION_SECONDS", raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()
    # Drop injectable hooks between tests so a leftover fake cannot leak.
    for name in ("stt_connect", "sample_pcm", "stream_admission"):
        if hasattr(app.state, name):
            delattr(app.state, name)


def _client() -> TestClient:
    clear_settings_cache()
    return TestClient(app)


def _recv_until(ws, wanted: set[str], timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    frames: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("type") in wanted:
            return frame
    raise AssertionError(f"no {wanted} frame in {frames!r}")


def test_missing_key_returns_error_frame_without_opening_upstream(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            frame = _recv_until(ws, {"error"})
            assert "GNANI_API_KEY" in frame["message"]
    assert connect.calls == []


def test_audio_reaches_upstream_before_browser_commit():
    """Audio must be forwarded to Prisma while the browser is still recording.

    A second binary frame is sent so the TestClient portal keeps running the
    pump. The first frame was queued before that, so the fake should see it
    before this test sends commit. The session is always committed so the
    socket exits cleanly even if the assertion fails.
    """
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_bytes(FRAME)
            ws.send_bytes(FRAME)
            socket = connect.sockets[0] if connect.sockets else None
            got_audio = bool(socket and socket.audio_received.wait(timeout=2))
            sent = list(socket.sent) if socket else []
            had_commit = any(_is_commit(m) for m in sent)
            ws.send_json({"type": "commit", "sample_rate": 16000})
            event = _recv_until(ws, {"event", "error"})
            assert got_audio, f"upstream did not receive audio before commit; sent={sent!r}"
            assert not had_commit
            assert event["type"] == "event"


def test_drain_then_commit_order():
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_bytes(FRAME)
            ws.send_bytes(FRAME)
            ws.send_bytes(FRAME)
            ws.send_json({"type": "commit", "sample_rate": 16000})
            event = _recv_until(ws, {"event", "error"})
            assert event["type"] == "event"
    sent = connect.sockets[0].sent
    binary = [i for i, m in enumerate(sent) if isinstance(m, (bytes, bytearray))]
    commits = [i for i, m in enumerate(sent) if _is_commit(m)]
    assert len(binary) == 3
    assert len(commits) == 1
    assert max(binary) < commits[0]
    assert all(len(sent[i]) == 1024 for i in binary)


def test_third_stream_is_rejected_without_opening_upstream():
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws1:
            with client.websocket_connect("/api/stream", headers=ORIGIN) as ws2:
                with client.websocket_connect("/api/stream", headers=ORIGIN) as ws3:
                    frame = _recv_until(ws3, {"error"})
                    assert "Too many" in frame["message"]
                # Hold the first two open so the cap still applies.
                assert connect.calls == []
            _ = ws1
            _ = ws2


def test_bad_origin_is_rejected():
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect(
            "/api/stream", headers={"Origin": "http://evil.example"}
        ) as ws:
            frame = _recv_until(ws, {"error"})
            assert "Origin" in frame["message"]
    assert connect.calls == []


def test_missing_origin_is_rejected():
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream") as ws:
            frame = _recv_until(ws, {"error"})
            assert "Origin" in frame["message"]
    assert connect.calls == []


def test_idle_timeout_closes_and_unregisters(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "0.25")
    monkeypatch.setenv("RASTA_STREAM_HEARTBEAT_SECONDS", "30")
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            frame = _recv_until(ws, {"error"}, timeout=3.0)
            assert "idle" in frame["message"].lower()
            with pytest.raises(WebSocketDisconnect):
                # The server closes after the error frame; the next receive should fail.
                ws.receive_json()
        assert len(client.app.state.stream_registry) == 0
        assert client.app.state.stream_slots.active == 0
    assert connect.calls == []  # idle before first audio: no upstream


def test_event_frame_is_stored_with_the_same_id():
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_bytes(FRAME)
            ws.send_json({"type": "commit", "sample_rate": 16000})
            event_frame = _recv_until(ws, {"event", "error"})
        assert event_frame["type"] == "event"
        assert event_frame["event"]["intent"] == "customer_unreachable"
        assert event_frame["event"]["order_id"] == "18"
        record_id = event_frame["id"]
        listed = attach_event_store(app).list_since(None)
        assert listed, "expected the event to be in the store"
        assert listed[-1]["id"] == record_id
        assert listed[-1]["event"]["intent"] == "customer_unreachable"
        assert event_frame["stt"]["request_id"] == "req-live"
