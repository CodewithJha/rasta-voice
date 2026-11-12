"""Realtime Prisma WebSocket session.

``stt.py`` keeps header construction and the REST client. This module is
the socket loop: a session that sends 1024-byte PCM frames, commits, and
yields parsed server frames. ``connect`` is injectable so tests never
open a real socket.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from gnani_client.env import require_api_key
from gnani_client.errors import GnaniError
from gnani_client.stt import PrismaSTT, SttResult, stream_headers

# Gnani requires exactly 1024-byte (512-sample) binary frames.
DEFAULT_FRAME_BYTES = 1024

Connect = Callable[..., AbstractAsyncContextManager[Any]]


class StreamHandshakeError(GnaniError):
    """The Prisma stream handshake was refused or could not be opened."""


def handshake_status(exc: BaseException) -> int | None:
    """Best-effort HTTP status from a websockets handshake failure."""
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    for attr in ("status_code", "status"):
        code = getattr(response, attr, None)
        if isinstance(code, int):
            return code
    return None


def default_connect() -> Connect:
    """Return ``websockets.connect``, which takes ``additional_headers`` (v13+)."""
    import websockets

    return websockets.connect


class SttStream:
    """One Prisma streaming session.

    ``send_audio`` does not sleep; the caller paces live or recorded audio.
    A short tail is zero-padded to ``frame_bytes`` on ``commit`` so every
    binary frame is exactly the size the server requires.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base: str | None = None,
        sample_rate: int = 16000,
        preset: str | None = None,
        output_format: str = "codemix",
        keyterms: list[str] | None = None,
        topic: str | None = None,
        idle_timeout_sec: int = 60,
        frame_bytes: int = DEFAULT_FRAME_BYTES,
        connect: Connect | None = None,
        model: str = "prisma-v3.0",
        language_code: str = "hi-IN,en-IN",
    ) -> None:
        if frame_bytes < 2 or frame_bytes % 2:
            raise ValueError("frame_bytes must be a positive even integer")
        self._key = require_api_key(api_key)
        self._url = PrismaSTT(key=self._key, base=base).stream_url
        self._headers = stream_headers(
            api_key=self._key,
            model=model,
            language_code=language_code,
            sample_rate=sample_rate,
            output_format=output_format,
            keyterms=keyterms,
            topic=topic,
            idle_timeout_sec=idle_timeout_sec,
            preset=preset,
        )
        self._frame_bytes = frame_bytes
        self._connect = connect or default_connect()
        self._buf = bytearray()
        self._cm: AbstractAsyncContextManager[Any] | None = None
        self._ws: Any = None

    @property
    def url(self) -> str:
        return self._url

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    async def __aenter__(self) -> SttStream:
        try:
            self._cm = self._connect(self._url, additional_headers=self._headers)
            self._ws = await self._cm.__aenter__()
        except StreamHandshakeError:
            self._cm = None
            self._ws = None
            raise
        except Exception as exc:
            self._cm = None
            self._ws = None
            status = handshake_status(exc)
            raise StreamHandshakeError(
                f"Prisma stream handshake failed{f' ({status})' if status else ''}",
                status=status,
            ) from exc
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._cm is None:
            return
        try:
            await self._cm.__aexit__(exc_type, exc, tb)
        except Exception:
            pass
        self._cm = None
        self._ws = None

    async def send_audio(self, pcm: bytes) -> None:
        if not pcm:
            return
        self._ws_or_raise()
        self._buf.extend(pcm)
        await self._flush_full_frames()

    async def commit(self) -> None:
        self._ws_or_raise()
        if self._buf:
            padding = self._frame_bytes - len(self._buf)
            await self._ws.send(bytes(self._buf) + bytes(padding))
            self._buf.clear()
        await self._ws.send(json.dumps({"type": "commit"}))

    async def frames(self) -> AsyncIterator[dict[str, Any]]:
        self._ws_or_raise()
        async for raw in self._ws:
            if not isinstance(raw, str):
                continue
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(frame, dict) and "type" in frame:
                yield frame

    def _ws_or_raise(self) -> Any:
        if self._ws is None:
            raise RuntimeError("SttStream must be used as an async context manager")
        return self._ws

    async def _flush_full_frames(self) -> None:
        size = self._frame_bytes
        while len(self._buf) >= size:
            frame = bytes(self._buf[:size])
            del self._buf[:size]
            await self._ws.send(frame)


def _request_id_from(frame: dict[str, Any]) -> str | None:
    value = frame.get("request_id")
    if isinstance(value, str) and value:
        return value
    segment = frame.get("segment_id")
    if isinstance(segment, str) and "-seg-" in segment:
        return segment.split("-seg-", 1)[0] or None
    return None


async def transcribe_pcm(
    pcm: bytes,
    sample_rate: int,
    *,
    connect: Connect | None = None,
    api_key: str | None = None,
    base: str | None = None,
    preset: str | None = None,
    output_format: str = "codemix",
    keyterms: list[str] | None = None,
    topic: str | None = None,
    model: str = "prisma-v3.0",
    language_code: str = "hi-IN,en-IN",
    idle_timeout_sec: int = 60,
    frame_bytes: int = DEFAULT_FRAME_BYTES,
) -> SttResult:
    """Send one PCM buffer, commit, and join transcript frames.

    This is a helper for tests and short clips. Live microphone audio
    must be pumped through :class:`SttStream` while it is captured.
    """
    texts: list[str] = []
    request_id: str | None = None
    detected: str | None = None
    async with SttStream(
        api_key=api_key,
        base=base,
        sample_rate=sample_rate,
        preset=preset,
        output_format=output_format,
        keyterms=keyterms,
        topic=topic,
        idle_timeout_sec=idle_timeout_sec,
        frame_bytes=frame_bytes,
        connect=connect,
        model=model,
        language_code=language_code,
    ) as stream:
        await stream.send_audio(pcm)
        await stream.commit()
        async for frame in stream.frames():
            kind = frame.get("type")
            if kind == "connected":
                request_id = _request_id_from(frame) or request_id
            elif kind == "transcript":
                text = frame.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
                request_id = request_id or _request_id_from(frame)
                lang = frame.get("detected_language_code")
                if isinstance(lang, str) and lang:
                    detected = lang
            elif kind == "error":
                message = frame.get("message")
                raise GnaniError(
                    message if isinstance(message, str) and message else "Prisma stream error"
                )
    return SttResult(
        transcript=" ".join(texts),
        model=model,
        request_id=request_id,
        detected_language_code=detected,
        success=True,
    )
