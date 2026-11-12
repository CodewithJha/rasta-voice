"""Process-wide stream slots, admission hook, and session registry.

Issue 07 owns the concurrent-stream cap and a lifespan hook that cancels
active sessions. Issue 13 replaces ``StreamAdmission`` on ``app.state``
with the real credit budget; the default always allows. Issue 29 can
reuse ``StreamRegistry.aclose``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from rasta.settings import get_settings


class StreamAdmission(Protocol):
    """Called after a stream slot is reserved and before Prisma or Timbre runs."""

    def allow(self) -> bool:
        """Return True to proceed, False to reject with no upstream opened."""


class AllowAllAdmission:
    """Default admission: issue 13 owns the real budget."""

    def allow(self) -> bool:
        return True


class StreamSlots:
    """Bounded concurrency that never queues a waiter.

    ``asyncio.Semaphore.acquire`` would park the third caller until a slot
    frees; the issue requires an immediate rejection and no upstream.
    """

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("stream slot limit must be a positive integer")
        self._limit = limit
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    async def try_acquire(self) -> bool:
        async with self._lock:
            if self._active >= self._limit:
                return False
            self._active += 1
            return True

    async def release(self) -> None:
        async with self._lock:
            if self._active:
                self._active -= 1


class StreamRegistry:
    """Active stream tasks, so lifespan shutdown can cancel them."""

    def __init__(self) -> None:
        self._sessions: set[asyncio.Task[Any]] = set()

    def add(self, task: asyncio.Task[Any]) -> None:
        self._sessions.add(task)

    def discard(self, task: asyncio.Task[Any]) -> None:
        self._sessions.discard(task)

    def __len__(self) -> int:
        return len(self._sessions)

    async def aclose(self) -> None:
        tasks = list(self._sessions)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._sessions.clear()


def attach_stream_runtime(app: Any, *, replace: bool = False) -> None:
    """Install slots, registry, and the default admission hook on ``app.state``.

    Lifespan calls this with ``replace=True``. Routes call it without, so a
    TestClient that skipped lifespan still has a runtime. ``stt_connect`` and
    a custom admission hook are left alone so tests can inject them before
    or after startup.
    """
    settings = get_settings()
    if replace or getattr(app.state, "stream_slots", None) is None:
        app.state.stream_slots = StreamSlots(settings.max_streams)
    if replace or getattr(app.state, "stream_registry", None) is None:
        app.state.stream_registry = StreamRegistry()
    if getattr(app.state, "stream_admission", None) is None:
        app.state.stream_admission = AllowAllAdmission()
