"""Prisma stream session against a fake ``connect`` defined in this file."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.stt_stream import StreamHandshakeError, SttStream, transcribe_pcm


class FakeSocket:
    """Minimal upstream: records sends, yields queued server frames."""

    def __init__(
        self,
        outgoing: list[str],
        *,
        transcripts_on_commit: list[dict[str, Any]] | None = None,
        error_on_commit: dict[str, Any] | None = None,
        refuse: Exception | None = None,
    ) -> None:
        self.sent: list[Any] = []
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        for frame in outgoing:
            self._queue.put_nowait(frame)
        self._transcripts = list(transcripts_on_commit or [])
        self._error = error_on_commit
        self._committed = False

    async def send(self, data: Any) -> None:
        self.sent.append(data)
        if not _is_commit(data) or self._committed:
            return
        self._committed = True
        if self._error is not None:
            await self._queue.put(json.dumps(self._error))
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
    """Callable with the ``connect(url, additional_headers=...)`` shape."""

    def __init__(
        self,
        *,
        outgoing: list[str] | None = None,
        transcripts_on_commit: list[dict[str, Any]] | None = None,
        error_on_commit: dict[str, Any] | None = None,
        refuse: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sockets: list[FakeSocket] = []
        self._outgoing = outgoing or [json.dumps({"type": "connected", "request_id": "req-stream"})]
        self._transcripts = transcripts_on_commit
        self._error = error_on_commit
        self._refuse = refuse

    def __call__(self, url: str, additional_headers: dict[str, str] | None = None, **_: Any):
        self.calls.append({"url": url, "headers": dict(additional_headers or {})})
        socket = FakeSocket(
            list(self._outgoing),
            transcripts_on_commit=list(self._transcripts or []),
            error_on_commit=self._error,
            refuse=self._refuse,
        )
        self.sockets.append(socket)
        return _FakeCM(socket, self._refuse)


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


def _pcm(frames: int, frame_bytes: int = 1024) -> bytes:
    # Non-zero samples so padding (zeros) is visible if a test looks.
    return bytes([1, 0]) * (frame_bytes // 2) * frames


def _run(coro):
    return asyncio.run(coro)


def test_transcribe_pcm_sends_1024_byte_frames_then_commit():
    async def body():
        connect = FakeConnect(
            transcripts_on_commit=[
                {
                    "type": "transcript",
                    "text": "bhaiya gate band hai",
                    "segment_id": "req-stream-seg-1",
                },
                {
                    "type": "transcript",
                    "text": "order eighteen",
                    "segment_id": "req-stream-seg-2",
                },
            ]
        )
        pcm = _pcm(2) + b"\x03\x00" * 10  # two full frames plus a short tail
        result = await transcribe_pcm(pcm, 16000, connect=connect, api_key="test-key")
        assert result.transcript == "bhaiya gate band hai order eighteen"
        assert result.request_id == "req-stream"
        assert len(connect.calls) == 1
        sent = connect.sockets[0].sent
        binary = [m for m in sent if isinstance(m, (bytes, bytearray))]
        assert all(len(m) == 1024 for m in binary)
        assert len(binary) == 3  # two full + one padded tail
        assert sum(binary[2][20:]) == 0  # tail padding is zeros
        assert _is_commit(sent[-1])
        assert all(isinstance(m, (bytes, bytearray)) for m in sent[:-1])

    _run(body())


def test_upstream_error_frame_is_raised():
    async def body():
        connect = FakeConnect(error_on_commit={"type": "error", "message": "STT engine failed"})
        with pytest.raises(GnaniError, match="STT engine failed"):
            await transcribe_pcm(_pcm(1), 16000, connect=connect, api_key="test-key")

    _run(body())


def test_handshake_refusal_surfaces_status():
    class Refused(Exception):
        def __init__(self) -> None:
            super().__init__("unauthorized")
            self.status = 401

    async def body():
        connect = FakeConnect(refuse=Refused())
        with pytest.raises(StreamHandshakeError, match="401") as info:
            await transcribe_pcm(_pcm(1), 16000, connect=connect, api_key="test-key")
        assert info.value.status == 401

    _run(body())


def test_url_path_is_stt_v3_stream():
    async def body():
        connect = FakeConnect(transcripts_on_commit=[{"type": "transcript", "text": "ok"}])
        await transcribe_pcm(
            _pcm(1),
            16000,
            connect=connect,
            api_key="test-key",
            base="https://api.vachana.ai",
        )
        assert connect.calls[0]["url"] == "wss://api.vachana.ai/stt/v3/stream"
        assert connect.calls[0]["url"].endswith("/stt/v3/stream")

    _run(body())


def test_telephony_preset_sets_sample_rate_8000():
    async def body():
        connect = FakeConnect(transcripts_on_commit=[{"type": "transcript", "text": "ok"}])
        await transcribe_pcm(
            _pcm(1),
            16000,
            connect=connect,
            api_key="test-key",
            preset="telephony",
        )
        headers = connect.calls[0]["headers"]
        assert headers["x-sample-rate"] == "8000"
        assert headers["x-api-key-id"] == "test-key"

    _run(body())


def test_missing_key_fails_before_connect(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)

    async def body():
        connect = FakeConnect()
        with pytest.raises(MissingApiKeyError):
            await transcribe_pcm(_pcm(1), 16000, connect=connect)
        assert connect.calls == []

    _run(body())


def test_session_send_audio_and_iter_frames_directly():
    async def body():
        connect = FakeConnect(
            transcripts_on_commit=[
                {"type": "transcript", "text": "hello", "segment_id": "abc-seg-1"}
            ]
        )
        texts: list[str] = []
        async with SttStream(api_key="k", connect=connect, sample_rate=16000) as stream:
            await stream.send_audio(_pcm(1))
            await stream.commit()
            async for frame in stream.frames():
                if frame.get("type") == "transcript":
                    texts.append(frame["text"])
        assert texts == ["hello"]

    _run(body())
