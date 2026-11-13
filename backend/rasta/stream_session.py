"""One supervised Prisma stream session.

Browser-in, upstream-out, upstream-in, and the watchdog are sibling tasks.
The first terminal condition sets a ``SessionOutcome`` and cancels the rest.
A single finalize path then either stores one event or stores nothing, and
always closes both sockets.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from gnani_client.stt import RIDER_KEYTERMS, RIDER_TOPIC
from gnani_client.stt_stream import (
    StreamHandshakeError,
    SttStream,
    handshake_status,
)
from rasta.extract import extract_event_with_source
from rasta.pipeline import STT_FORMAT
from rasta.request_id import log_gnani_call
from rasta.settings import Settings
from rasta.store import attach_event_store, bind_rider_header, reset_rider_header
from rasta.tasks import cancel_all, first_completed

log = logging.getLogger("rasta.stream")

# Live Prisma stream rejects a comma-separated language list (REST still
# accepts hi-IN,en-IN). transliterate sessions default to indic-auto.
STREAM_LANGUAGE_CODE = "indic-auto"

CLOSE_OK = 1000
CLOSE_IDLE = 1001
CLOSE_POLICY = 1008
CLOSE_ERROR = 1011
CLOSE_BUSY = 1013
CLOSE_NO_KEY = 4401
CLOSE_ORIGIN = 4403

Produce = Callable[[SttStream], Awaitable[None]]


class SessionOutcome(Enum):
    COMPLETED = "completed"
    EMPTY = "empty"
    UPSTREAM_ERROR = "upstream_error"
    HANDSHAKE_ERROR = "handshake_error"
    IDLE_TIMEOUT = "idle_timeout"
    SESSION_CAP = "session_cap"
    BROWSER_GONE = "browser_gone"
    FAILED = "failed"


_CLOSE_FOR = {
    SessionOutcome.COMPLETED: CLOSE_OK,
    SessionOutcome.EMPTY: CLOSE_OK,
    SessionOutcome.UPSTREAM_ERROR: CLOSE_ERROR,
    SessionOutcome.HANDSHAKE_ERROR: CLOSE_ERROR,
    SessionOutcome.IDLE_TIMEOUT: CLOSE_IDLE,
    SessionOutcome.SESSION_CAP: CLOSE_IDLE,
    SessionOutcome.BROWSER_GONE: CLOSE_OK,
    SessionOutcome.FAILED: CLOSE_ERROR,
}

_MESSAGE_FOR = {
    SessionOutcome.EMPTY: "No transcript received",
    SessionOutcome.IDLE_TIMEOUT: "Stream idle timeout",
    SessionOutcome.SESSION_CAP: "Stream session expired",
    SessionOutcome.FAILED: "Stream failed",
}


class StreamSession:
    """Run one accepted ``/api/stream`` conversation to a single outcome."""

    def __init__(
        self,
        websocket: WebSocket,
        app: Any,
        settings: Settings,
        *,
        queue: asyncio.Queue[bytes | None] | None = None,
        commit: asyncio.Event | None = None,
        produce: Produce | None = None,
    ) -> None:
        self.websocket = websocket
        self.app = app
        self.settings = settings
        self.queue = queue
        self.commit = commit
        self.produce = produce
        self.outcome: SessionOutcome | None = None
        self.message: str | None = None
        self.texts: list[str] = []
        self.request_id: str | None = None
        self._done = asyncio.Event()
        self._last_activity = time.monotonic()
        self._last_transcript_at = self._last_activity
        self._got_frame = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._finalized = False

    @property
    def done(self) -> asyncio.Event:
        return self._done

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    def resolve(self, outcome: SessionOutcome, message: str | None = None) -> bool:
        """Record the first terminal condition. Later calls are ignored."""
        if self.outcome is not None:
            return False
        self.outcome = outcome
        if message is not None:
            self.message = message
        elif outcome in _MESSAGE_FOR:
            self.message = _MESSAGE_FOR[outcome]
        self._done.set()
        return True

    def _gnani_status(self) -> int | str:
        if self.outcome is None:
            return "error"
        if self.outcome is SessionOutcome.COMPLETED:
            return 200
        return self.outcome.value

    async def run(self) -> None:
        started = time.perf_counter()
        try:
            async with _open_stream(self.app, self.settings) as stream:
                self._tasks = [
                    asyncio.create_task(self._uplink(stream), name="stream-uplink"),
                    asyncio.create_task(self._downlink(stream), name="stream-downlink"),
                    asyncio.create_task(self._browser_in(), name="stream-browser"),
                    asyncio.create_task(self._watchdog(), name="stream-watchdog"),
                ]
                await self._done.wait()
                # Finalize (error/event + close) while the browser socket is
                # still connected. Cancelling an in-flight receive first can
                # drop the close frame.
                await self._finalize()
                await _cancel_tasks(self._tasks)
        except StreamHandshakeError as exc:
            self.resolve(SessionOutcome.HANDSHAKE_ERROR, handshake_message(exc))
        except Exception:
            log.exception("Stream session failed")
            self.resolve(SessionOutcome.FAILED)
        finally:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self._finalize()
            await _cancel_tasks(self._tasks)
            log_gnani_call(
                endpoint="stt_stream",
                latency_ms=max(0, int(round((time.perf_counter() - started) * 1000))),
                status=self._gnani_status(),
                gnani_request_id=self.request_id,
                audio_seconds=None,
            )

    async def _uplink(self, stream: SttStream) -> None:
        try:
            if self.produce is not None:
                await self.produce(stream)
            else:
                await self._live_uplink(stream)
            if self.outcome is not None:
                return
            down = _task_named(self._tasks, "stream-downlink")
            committed_at = time.monotonic()
            await _drain_transcripts(
                down,
                self._got_frame,
                self.texts,
                lambda: max(self._last_transcript_at, committed_at),
                self._done,
                self.settings,
            )
            if self.outcome is not None:
                return
            if self.texts:
                self.resolve(SessionOutcome.COMPLETED)
            else:
                self.resolve(SessionOutcome.EMPTY)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Upstream send failed: %s", exc)
            self.resolve(SessionOutcome.UPSTREAM_ERROR, "Prisma stream error")

    async def _live_uplink(self, stream: SttStream) -> None:
        assert self.queue is not None and self.commit is not None
        while self.outcome is None:
            if self.commit.is_set():
                while not self.queue.empty():
                    chunk = self.queue.get_nowait()
                    if chunk:
                        await stream.send_audio(chunk)
                await stream.commit()
                return
            index, chunk = await first_completed(
                self.queue.get(), self.commit.wait(), self._done.wait()
            )
            if index == 0 and chunk:
                await stream.send_audio(chunk)

    async def _downlink(self, stream: SttStream) -> None:
        try:
            async for frame in stream.frames():
                if self.outcome is not None and self.outcome is not SessionOutcome.COMPLETED:
                    return
                kind = frame.get("type")
                if kind == "connected":
                    self.request_id = _request_id(frame) or self.request_id
                elif kind == "transcript":
                    text = frame.get("text")
                    if isinstance(text, str) and text.strip():
                        self.texts.append(text.strip())
                        self._last_transcript_at = time.monotonic()
                        self._got_frame.set()
                        await send_json(
                            self.websocket, {"type": "transcript", "text": text.strip()}
                        )
                    self.request_id = self.request_id or _request_id(frame)
                elif kind == "error":
                    message = frame.get("message")
                    self.resolve(
                        SessionOutcome.UPSTREAM_ERROR,
                        message if isinstance(message, str) and message else "Prisma stream error",
                    )
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Upstream receive failed: %s", exc)
            self.resolve(SessionOutcome.UPSTREAM_ERROR, "Prisma stream error")

    async def _browser_in(self) -> None:
        """Watch the browser for the whole session, live and sample."""
        try:
            while self.outcome is None:
                message = await receive_or_done(self.websocket, self._done)
                if message is None:
                    return
                if message["kind"] == "disconnect":
                    self.resolve(SessionOutcome.BROWSER_GONE)
                    return
                if self.produce is not None:
                    continue
                self.touch()
                if message["kind"] == "bytes" and self.queue is not None:
                    await self.queue.put(message["data"])
                    continue
                if message["kind"] == "text":
                    control = parse_control(message["data"])
                    if control and control.get("type") == "commit" and self.commit is not None:
                        self.commit.set()
        except asyncio.CancelledError:
            raise
        except WebSocketDisconnect:
            self.resolve(SessionOutcome.BROWSER_GONE)
        except Exception as exc:
            log.warning("Browser socket failed: %s", exc)
            self.resolve(SessionOutcome.BROWSER_GONE)

    async def _watchdog(self) -> None:
        deadline = time.monotonic() + self.settings.stream_session_seconds
        next_ping = time.monotonic() + self.settings.stream_heartbeat_seconds
        while self.outcome is None:
            now = time.monotonic()
            if now - self._last_activity >= self.settings.stream_idle_seconds:
                self.resolve(SessionOutcome.IDLE_TIMEOUT)
                return
            if now >= deadline:
                self.resolve(SessionOutcome.SESSION_CAP)
                return
            if now >= next_ping:
                await send_json(self.websocket, {"type": "ping"})
                next_ping = now + self.settings.stream_heartbeat_seconds
            wait = min(
                self.settings.stream_idle_seconds - (now - self._last_activity),
                deadline - now,
                next_ping - now,
            )
            index, _ = await first_completed(self._done.wait(), timeout=max(0.0, wait))
            if index == 0:
                return

    async def _finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True
        outcome = self.outcome or SessionOutcome.FAILED
        try:
            if outcome is SessionOutcome.COMPLETED:
                await _emit_event(self.websocket, self.app, self.texts, self.request_id)
            elif outcome is not SessionOutcome.BROWSER_GONE:
                await send_error(
                    self.websocket, self.message or _MESSAGE_FOR[SessionOutcome.FAILED]
                )
        finally:
            await close_socket(self.websocket, _CLOSE_FOR[outcome])


def _open_stream(app: Any, settings: Settings) -> SttStream:
    connect = getattr(app.state, "stt_connect", None)
    return SttStream(
        sample_rate=settings.stream_sample_rate,
        output_format=STT_FORMAT,
        language_code=STREAM_LANGUAGE_CODE,
        keyterms=RIDER_KEYTERMS,
        topic=RIDER_TOPIC,
        idle_timeout_sec=settings.prisma_idle_timeout_sec(),
        frame_bytes=settings.stream_frame_bytes,
        connect=connect,
    )


async def _drain_transcripts(
    down_task: asyncio.Task[Any] | None,
    got_frame: asyncio.Event,
    texts: list[str],
    last_transcript_at: Callable[[], float],
    done: asyncio.Event,
    settings: Settings,
) -> None:
    """Wait for trailing Prisma transcripts after commit, then return.

    Prisma does not always close the socket after ``commit``. Once at least
    one transcript has arrived, a quiet gap is enough. Abort early if the
    session has already resolved (error, disconnect, timeout).
    """
    deadline = time.monotonic() + settings.stream_drain_seconds
    while (
        (down_task is None or not down_task.done())
        and not done.is_set()
        and time.monotonic() < deadline
    ):
        if texts:
            remaining = last_transcript_at() + settings.stream_quiet_seconds - time.monotonic()
            if remaining <= 0:
                return
        else:
            remaining = deadline - time.monotonic()
        got_frame.clear()
        await first_completed(got_frame.wait(), done.wait(), timeout=max(0.0, remaining))
        quiet = last_transcript_at() + settings.stream_quiet_seconds
        if done.is_set() or (texts and time.monotonic() >= quiet):
            return
    if down_task is not None and down_task.done():
        exc = down_task.exception() if not down_task.cancelled() else None
        if exc is not None:
            raise exc


async def _emit_event(
    websocket: WebSocket,
    app: Any,
    texts: list[str],
    request_id: str | None,
) -> None:
    transcript = " ".join(texts).strip()
    extracted = await asyncio.to_thread(extract_event_with_source, transcript)
    payload = {
        "transcript": transcript,
        "stt": {
            "model": "prisma-v3.0",
            "request_id": request_id,
            "detected_language_code": None,
            "processing_time": None,
            "audio_seconds": None,
        },
        "event": extracted.event.model_dump(mode="json"),
        "extractor_source": extracted.source,
        "fallback_reason": extracted.fallback_reason,
    }
    header = None
    for key, value in (websocket.headers.items() if hasattr(websocket, "headers") else []):
        if key.lower() == "x-rider-id":
            header = value
            break
    token = bind_rider_header(header)
    try:
        stamped = attach_event_store(app).append(payload)
    finally:
        reset_rider_header(token)
    await send_json(websocket, {"type": "event", **stamped})
    log.info("stream event id=%s request_id=%s", stamped.get("id"), request_id)


def _request_id(frame: dict[str, Any]) -> str | None:
    value = frame.get("request_id")
    if isinstance(value, str) and value:
        return value
    segment = frame.get("segment_id")
    if isinstance(segment, str) and "-seg-" in segment:
        return segment.split("-seg-", 1)[0] or None
    return None


def _task_named(tasks: list[asyncio.Task[Any]], name: str) -> asyncio.Task[Any] | None:
    for task in tasks:
        if task.get_name() == name:
            return task
    return None


async def _cancel_tasks(tasks: list[asyncio.Task[Any]]) -> None:
    await cancel_all(tasks)
    tasks.clear()


def handshake_message(exc: StreamHandshakeError) -> str:
    status = exc.status or handshake_status(exc)
    if status == 401:
        return "Prisma refused the handshake (401)"
    if status == 402:
        return "Prisma refused the handshake (402)"
    if status == 429:
        return "Prisma refused the handshake (429)"
    return "Could not open a Prisma stream"


def parse_control(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


async def receive_message(websocket: WebSocket, timeout: float) -> dict[str, Any] | None:
    """Return a parsed browser frame, or None on timeout."""
    try:
        index, message = await first_completed(websocket.receive(), timeout=timeout)
    except WebSocketDisconnect:
        return {"kind": "disconnect"}
    if index is None:
        return None
    return _parse_ws_message(message)


async def receive_or_done(websocket: WebSocket, done: asyncio.Event) -> dict[str, Any] | None:
    """Return a browser frame, or None if the session already resolved."""
    try:
        index, message = await first_completed(websocket.receive(), done.wait())
    except WebSocketDisconnect:
        return {"kind": "disconnect"}
    if index != 0:
        return None
    return _parse_ws_message(message)


def _parse_ws_message(message: dict[str, Any]) -> dict[str, Any]:
    typ = message.get("type")
    if typ == "websocket.disconnect":
        return {"kind": "disconnect"}
    if typ == "websocket.receive":
        data = message.get("bytes")
        if isinstance(data, (bytes, bytearray)):
            return {"kind": "bytes", "data": bytes(data)}
        text = message.get("text")
        if isinstance(text, str):
            return {"kind": "text", "data": text}
    return {"kind": "disconnect"}


async def send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_json(payload)
    except Exception:
        return


async def send_error(websocket: WebSocket, message: str) -> None:
    await send_json(websocket, {"type": "error", "message": message})


async def close_socket(websocket: WebSocket, code: int) -> None:
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.close(code=code)
    except Exception:
        return


async def fail(websocket: WebSocket, message: str, code: int) -> None:
    await send_error(websocket, message)
    await close_socket(websocket, code)
