"""Owned first-completed waits.

Every child task is cancelled and awaited on every exit, including when
the caller itself is cancelled. Callers must not spawn waiters with
``asyncio.create_task`` and ``asyncio.wait`` of their own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any


async def cancel_all(tasks: Iterable[asyncio.Task[Any]]) -> None:
    """Cancel every task and await them so they cannot leak."""
    owned = list(tasks)
    for task in owned:
        task.cancel()
    if owned:
        await asyncio.gather(*owned, return_exceptions=True)


async def first_completed(
    *awaitables: Awaitable[Any],
    timeout: float | None = None,
) -> tuple[int | None, Any]:
    """Return ``(index, result)`` of the first awaitable that finishes.

    On timeout the result is ``(None, None)``. A ``finally`` block always
    cancels and awaits every child. An exception from the winning task is
    raised after that cleanup.
    """
    if not awaitables:
        raise TypeError("first_completed() requires at least one awaitable")
    tasks: list[asyncio.Task[Any]] = [
        asyncio.create_task(item, name="first-completed")  # type: ignore[arg-type]
        for item in awaitables
    ]
    try:
        done, _pending = await asyncio.wait(
            tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if not done:
            return None, None
        winner = min(done, key=tasks.index)
        if winner.cancelled():
            raise asyncio.CancelledError
        exc = winner.exception()
        if exc is not None:
            raise exc
        return tasks.index(winner), winner.result()
    finally:
        await cancel_all(tasks)


async def run_until_stopped(
    func: Callable[[], object],
    interval: float,
    stopped: asyncio.Event,
) -> None:
    """Call ``func`` immediately, then every ``interval`` seconds until stopped.

    ``stopped`` is the only way this loop ends. The wait is owned by
    ``first_completed`` so the interval sleep cannot leak on shutdown.
    """
    if interval <= 0:
        raise ValueError("interval must be a positive number of seconds")
    func()
    while not stopped.is_set():
        index, _result = await first_completed(stopped.wait(), asyncio.sleep(interval))
        if index == 0:
            return
        func()


def start_task(
    awaitable: Awaitable[Any],
    *,
    name: str,
) -> asyncio.Task[Any]:
    """Spawn one owned background task. Callers must cancel and await it."""
    return asyncio.create_task(awaitable, name=name)  # type: ignore[arg-type]
