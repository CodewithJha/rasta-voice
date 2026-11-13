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
        *,
        hold_audio: threading.Event | None = None,
        error_on_audio: dict[str, Any] | None = None,
    ) -> None:
        self.sent: list[Any] = []
        self.audio_received = threading.Event()
        self.closed = threading.Event()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        for frame in outgoing:
            self._queue.put_nowait(frame)
        self._transcripts = list(transcripts_on_commit)
        self._committed = False
        self._hold_audio = hold_audio
        self._error_on_audio = error_on_audio
        self._error_emitted = False

    async def send(self, data: Any) -> None:
        self.sent.append(data)
        if isinstance(data, (bytes, bytearray)):
            self.audio_received.set()
            if self._error_on_audio is not None and not self._error_emitted:
                self._error_emitted = True
                await self._queue.put(json.dumps(self._error_on_audio))
            if self._hold_audio is not None:
                while not self._hold_audio.is_set() and not self.closed.is_set():
                    await asyncio.sleep(0.01)
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
        if not self.closed.is_set():
            self.closed.set()
            await self._queue.put(None)


class FakeConnect:
    def __init__(
        self,
        *,
        transcripts: list[dict[str, Any]] | None = None,
        refuse: Exception | None = None,
        hold_audio: threading.Event | None = None,
        error_on_audio: dict[str, Any] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sockets: list[FakeSocket] = []
        self.started = threading.Event()
        self.transcripts = (
            [
                {
                    "type": "transcript",
                    "text": SAMPLE_LINE,
                    "segment_id": "req-live-seg-1",
                }
            ]
            if transcripts is None
            else list(transcripts)
        )
        self.refuse = refuse
        self.hold_audio = hold_audio
        self.error_on_audio = error_on_audio
        self.outgoing = [json.dumps({"type": "connected", "request_id": "req-live"})]

    def __call__(self, url: str, additional_headers: dict[str, str] | None = None, **_: Any):
        self.calls.append({"url": url, "headers": dict(additional_headers or {})})
        socket = FakeSocket(
            self.outgoing,
            self.transcripts,
            self.refuse,
            hold_audio=self.hold_audio,
            error_on_audio=self.error_on_audio,
        )
        self.sockets.append(socket)
        self.started.set()
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
    monkeypatch.delenv("RASTA_STREAM_QUIET_SECONDS", raising=False)
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
            socket = _wait_audio(connect)
            got_audio = True
            sent = list(socket.sent)
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


def _assert_cleanup(client: TestClient, connect: FakeConnect, *, upstream: str) -> None:
    """upstream: 'open' | 'none' | 'attempted' (handshake refused after connect())."""
    assert len(client.app.state.stream_registry) == 0
    assert client.app.state.stream_slots.active == 0
    if upstream == "open":
        assert connect.sockets, "expected an upstream socket"
        assert connect.sockets[0].closed.is_set()
    elif upstream == "none":
        assert connect.calls == []
    elif upstream == "attempted":
        assert connect.calls
        assert all(not socket.closed.is_set() for socket in connect.sockets)
    else:
        raise AssertionError(upstream)


def _wait_started(connect: FakeConnect, timeout: float = 2.0) -> FakeSocket:
    """Wait for the fake Prisma connect hook to run, then return its socket."""
    if not connect.started.wait(timeout=timeout):
        raise AssertionError("upstream did not start")
    if not connect.sockets:
        raise AssertionError("start signal set but no upstream socket")
    return connect.sockets[0]


def _wait_audio(connect: FakeConnect, timeout: float = 2.0) -> FakeSocket:
    """Wait until the first upstream audio frame has been received."""
    socket = _wait_started(connect, timeout=timeout)
    if not socket.audio_received.wait(timeout=timeout):
        raise AssertionError("upstream did not receive audio")
    return socket


def _stored() -> list[dict[str, Any]]:
    return attach_event_store(app).list_since(None)


def _collect_until_close(ws, timeout: float = 8.0) -> tuple[list[dict[str, Any]], int | None]:
    """Receive JSON frames until the server closes the socket."""
    deadline = time.monotonic() + timeout
    frames: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        try:
            message = ws.receive()
        except WebSocketDisconnect as exc:
            return frames, exc.code
        typ = message.get("type")
        if typ == "websocket.close":
            return frames, int(message.get("code") or 1000)
        text = message.get("text")
        if typ == "websocket.send" and text:
            frame = json.loads(text)
            if frame.get("type") != "ping":
                frames.append(frame)
    raise AssertionError(f"socket did not close; frames={frames!r}")


def test_upstream_error_after_transcript_does_not_store_event():
    connect = FakeConnect(
        transcripts=[
            {
                "type": "transcript",
                "text": SAMPLE_LINE,
                "segment_id": "req-live-seg-1",
            },
            {"type": "error", "message": "STT engine failed"},
        ]
    )
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_bytes(FRAME)
            ws.send_json({"type": "commit", "sample_rate": 16000})
            frames, code = _collect_until_close(ws)
        kinds = [frame["type"] for frame in frames]
        assert "transcript" in kinds
        assert "error" in kinds
        assert "event" not in kinds
        assert any("STT engine failed" in (frame.get("message") or "") for frame in frames)
        assert code == 1011
        assert _stored() == []
        _assert_cleanup(client, connect, upstream="open")


def test_idle_timeout_after_audio_closes_and_cleans_up(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "0.15")
    monkeypatch.setenv("RASTA_STREAM_HEARTBEAT_SECONDS", "30")
    monkeypatch.setenv("RASTA_STREAM_SESSION_SECONDS", "30")
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_bytes(FRAME)
            frames, code = _collect_until_close(ws)
        assert any("idle" in (frame.get("message") or "").lower() for frame in frames)
        assert all(frame.get("type") != "event" for frame in frames)
        assert code == 1001
        assert _stored() == []
        _assert_cleanup(client, connect, upstream="open")


def test_session_cap_after_audio_closes_and_cleans_up(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "30")
    monkeypatch.setenv("RASTA_STREAM_HEARTBEAT_SECONDS", "30")
    monkeypatch.setenv("RASTA_STREAM_SESSION_SECONDS", "0.15")
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_bytes(FRAME)
            frames, code = _collect_until_close(ws)
        assert any("expired" in (frame.get("message") or "").lower() for frame in frames)
        assert all(frame.get("type") != "event" for frame in frames)
        assert code == 1001
        assert _stored() == []
        _assert_cleanup(client, connect, upstream="open")


def test_sample_disconnect_does_not_store_event():
    hold = threading.Event()
    connect = FakeConnect(hold_audio=hold)
    try:
        with _client() as client:
            app.state.stt_connect = connect
            app.state.sample_pcm = lambda: FRAME * 3
            with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
                ws.send_json({"type": "sample"})
                _wait_audio(connect)
                ws.close()
                # Let the session finish cleanup before TestClient cancels the ASGI task.
                hold.set()
            assert _stored() == []
            assert not any(_is_commit(m) for m in connect.sockets[0].sent)
            _assert_cleanup(client, connect, upstream="open")
    finally:
        hold.set()


def _start(mode: str, ws) -> None:
    if mode == "sample":
        ws.send_json({"type": "sample"})
    else:
        ws.send_bytes(FRAME)


def _finish_live(ws) -> None:
    ws.send_json({"type": "commit", "sample_rate": 16000})


@pytest.mark.parametrize(
    "mode,condition",
    [
        ("live", "completed"),
        ("live", "empty"),
        ("live", "upstream_error"),
        ("live", "upstream_error_while_recording"),
        ("live", "handshake_error"),
        ("live", "idle_timeout"),
        ("live", "session_cap"),
        ("live", "browser_gone"),
        ("sample", "completed"),
        ("sample", "empty"),
        ("sample", "upstream_error"),
        ("sample", "handshake_error"),
        ("sample", "idle_timeout"),
        ("sample", "session_cap"),
        ("sample", "browser_gone"),
    ],
)
def test_session_outcome_table(mode: str, condition: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_STREAM_HEARTBEAT_SECONDS", "30")
    monkeypatch.setenv("RASTA_STREAM_QUIET_SECONDS", "0.05")
    monkeypatch.setenv("RASTA_STREAM_DRAIN_SECONDS", "0.3")
    if condition in {"idle_timeout"}:
        monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "0.15")
        monkeypatch.setenv("RASTA_STREAM_SESSION_SECONDS", "30")
    elif condition in {"session_cap"}:
        monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "30")
        monkeypatch.setenv("RASTA_STREAM_SESSION_SECONDS", "0.15")
    else:
        monkeypatch.setenv("RASTA_STREAM_IDLE_SECONDS", "30")
        monkeypatch.setenv("RASTA_STREAM_SESSION_SECONDS", "30")

    hold: threading.Event | None = None
    error_on_audio = None
    refuse = None
    transcripts: list[dict[str, Any]] | None = [
        {"type": "transcript", "text": SAMPLE_LINE, "segment_id": "req-live-seg-1"}
    ]
    expect_append = False
    expect_event = False
    expect_error = False
    expect_close: int | None = 1000
    error_snippet = ""

    if condition == "completed":
        expect_append = True
        expect_event = True
        expect_close = 1000
    elif condition == "empty":
        transcripts = []
        expect_error = True
        error_snippet = "No transcript"
        expect_close = 1000
    elif condition == "upstream_error":
        transcripts = [
            {"type": "transcript", "text": SAMPLE_LINE, "segment_id": "req-live-seg-1"},
            {"type": "error", "message": "STT engine failed"},
        ]
        expect_error = True
        error_snippet = "STT engine failed"
        expect_close = 1011
    elif condition == "upstream_error_while_recording":
        error_on_audio = {"type": "error", "message": "STT engine failed"}
        expect_error = True
        error_snippet = "STT engine failed"
        expect_close = 1011
    elif condition == "handshake_error":

        class Refused(Exception):
            def __init__(self) -> None:
                super().__init__("unauthorized")
                self.status = 401

        refuse = Refused()
        expect_error = True
        error_snippet = "401"
        expect_close = 1011
    elif condition == "idle_timeout":
        hold = threading.Event()
        expect_error = True
        error_snippet = "idle"
        expect_close = 1001
    elif condition == "session_cap":
        hold = threading.Event()
        expect_error = True
        error_snippet = "expired"
        expect_close = 1001
    elif condition == "browser_gone":
        hold = threading.Event()
        expect_close = None
    else:
        raise AssertionError(condition)

    connect = FakeConnect(
        transcripts=transcripts,
        refuse=refuse,
        hold_audio=hold,
        error_on_audio=error_on_audio,
    )
    try:
        with _client() as client:
            app.state.stt_connect = connect
            if mode == "sample":
                app.state.sample_pcm = lambda: FRAME * 3
            with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
                _start(mode, ws)
                if condition in {"idle_timeout", "session_cap", "browser_gone"}:
                    _wait_audio(connect)
                    if condition == "browser_gone":
                        ws.close()
                        frames, code = [], None
                    else:
                        frames, code = _collect_until_close(ws)
                else:
                    if mode == "live" and condition in {
                        "completed",
                        "empty",
                        "upstream_error",
                    }:
                        _finish_live(ws)
                    frames, code = _collect_until_close(ws)

                if condition != "browser_gone":
                    kinds = [frame["type"] for frame in frames]
                    if expect_event:
                        assert "event" in kinds
                    else:
                        assert "event" not in kinds
                    if expect_error:
                        assert "error" in kinds
                        assert any(
                            error_snippet.lower() in (frame.get("message") or "").lower()
                            for frame in frames
                        )
                    assert code == expect_close
                if hold is not None:
                    hold.set()
            stored = _stored()
            if expect_append:
                assert stored
            else:
                assert stored == []
            _assert_cleanup(
                client,
                connect,
                upstream="attempted" if condition == "handshake_error" else "open",
            )
    finally:
        if hold is not None:
            hold.set()



def test_stream_sample_budget_one_does_not_run_synthesis(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_DEMO_SPEECH_BUDGET", "1")
    called = {"timbre": 0}

    def pcm() -> bytes:
        called["timbre"] += 1
        return FRAME * 3

    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        app.state.sample_pcm = pcm
        with client.websocket_connect("/api/stream", headers=ORIGIN) as ws:
            ws.send_json({"type": "sample"})
            frame = _recv_until(ws, {"error"})
            assert "exhausted" in frame["message"].lower()
    assert called["timbre"] == 0
    assert connect.calls == []
    assert _stored() == []


def test_same_origin_stream_works_when_cors_allow_list_is_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "")
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "false")
    connect = FakeConnect()
    with _client() as client:
        app.state.stt_connect = connect
        with client.websocket_connect(
            "/api/stream",
            headers={"Origin": "http://testserver", "Host": "testserver"},
        ) as ws:
            ws.send_bytes(FRAME)
            ws.send_bytes(FRAME)
            socket = _wait_audio(connect)
            ws.send_json({"type": "commit", "sample_rate": 16000})
            event = _recv_until(ws, {"event", "error"})
            assert event["type"] == "event"
            assert socket is not None
