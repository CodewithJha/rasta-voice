"""Owned first-completed waits.

Every child task is cancelled and awaited on every exit, including when
the caller itself is cancelled. Callers must not spawn waiters with
``asyncio.create_task`` and ``asyncio.wait`` of their own.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterable
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
    tasks = [
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
