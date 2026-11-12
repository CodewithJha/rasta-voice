"""Session-level leak regression: child waiters must not survive run()."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.websockets import WebSocketState
from test_routes_stream import FRAME, FakeConnect

from rasta.settings import clear_settings_cache, get_settings
from rasta.store import attach_event_store
from rasta.stream_session import StreamSession


class FakeBrowser:
    """In-loop browser socket: receive() hangs until a message or close."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTED
        self._incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.close_code: int | None = None

    async def receive(self) -> dict[str, Any]:
        return await self._incoming.get()

    async def send_json(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.client_state = WebSocketState.DISCONNECTED
        self.close_code = code

    def hang_up(self) -> None:
        self.client_state = WebSocketState.DISCONNECTED
        self._incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # SttStream still requires a key even when connect is injected.
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    clear_settings_cache()
    yield
    clear_settings_cache()


def _pending() -> set[asyncio.Task]:
    return asyncio.all_tasks() - {asyncio.current_task()}


async def _settle() -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)


async def _wait_flag(flag: threading.Event, timeout: float = 2.0) -> None:
    if not await asyncio.to_thread(flag.wait, timeout):
        raise AssertionError("upstream did not start")


def _app(connect: FakeConnect) -> Any:
    app = SimpleNamespace()
    app.state = SimpleNamespace(stt_connect=connect)
    attach_event_store(app, replace=True)
    return app


def _settings(*, idle: float = 30.0, session: float = 30.0, heartbeat: float = 30.0):
    return replace(
        get_settings(),
        stream_idle_seconds=idle,
        stream_session_seconds=session,
        stream_heartbeat_seconds=heartbeat,
        stream_drain_seconds=0.3,
        stream_quiet_seconds=0.05,
    )


def _live_session(
    websocket: FakeBrowser, app: Any, settings, *, frame: bool = True
) -> StreamSession:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    if frame:
        queue.put_nowait(FRAME)
    return StreamSession(websocket, app, settings, queue=queue, commit=asyncio.Event())


def _sample_session(websocket: FakeBrowser, app: Any, settings) -> StreamSession:
    holder: list[StreamSession] = []

    async def produce(stream) -> None:
        session = holder[0]
        await stream.send_audio(FRAME)
        session.touch()
        await session.done.wait()

    session = StreamSession(websocket, app, settings, produce=produce)
    holder.append(session)
    return session


@pytest.mark.parametrize("mode", ["live", "sample"])
@pytest.mark.parametrize(
    "condition",
    ["timeout", "browser_gone", "upstream_error", "session_cap", "shutdown"],
)
def test_repeated_sessions_do_not_leak_child_tasks(mode: str, condition: str):
    async def body() -> None:
        before = _pending()
        for _ in range(3):
            await _run_one(mode, condition)
            await _settle()
        await _settle()
        assert _pending() == before

    asyncio.run(body())


async def _run_one(mode: str, condition: str) -> None:
    error_on_audio = (
        {"type": "error", "message": "STT engine failed"} if condition == "upstream_error" else None
    )
    connect = FakeConnect(error_on_audio=error_on_audio)
    if condition == "timeout":
        settings = _settings(idle=0.02, session=30.0)
    elif condition == "session_cap":
        settings = _settings(idle=30.0, session=0.02)
    else:
        settings = _settings(idle=30.0, session=30.0)
    app = _app(connect)
    websocket = FakeBrowser()
    session = (
        _sample_session(websocket, app, settings)
        if mode == "sample"
        else _live_session(websocket, app, settings)
    )
    if condition == "shutdown":
        task = asyncio.create_task(session.run())
        await _wait_flag(connect.started)
        await _settle()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return
    task = asyncio.create_task(session.run())
    await _wait_flag(connect.started)
    if condition == "browser_gone":
        await _wait_flag(connect.sockets[0].audio_received)
        websocket.hang_up()
    await asyncio.wait_for(task, timeout=2.0)
