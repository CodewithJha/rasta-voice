"""In-process dispatch event store. A restart clears the desk."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from rasta.settings import get_settings

# One lock for installing the process-wide store onto app.state.
_attach_lock = threading.Lock()


class InvalidSince(ValueError):
    """Raised when ``list_since`` cannot parse or cannot use ``since``."""


def parse_since(since: str) -> datetime:
    """Parse a tz-aware ISO 8601 timestamp.

    A trailing ``Z`` is accepted as UTC. Naive (no timezone) or malformed
    values raise ``InvalidSince`` so the router can answer 422.
    """
    text = since.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidSince(
            "since must be a timezone-aware UTC ISO 8601 timestamp"
        ) from exc
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise InvalidSince("since must be a timezone-aware UTC ISO 8601 timestamp")
    return value.astimezone(UTC)


class EventStore:
    """Append-only ring of recent ingest records, oldest first.

    Capacity is injected (from settings). ``append`` and ``list_since``
    copy on the way in and out so callers cannot alias stored dicts.
    ``created_at`` is UTC ISO 8601 and strictly monotonic in this process
    so a ``?since=<last created_at>`` poll cannot miss a later append.
    """

    def __init__(
        self,
        capacity: int,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._events: list[dict[str, Any]] = []
        # ponytail: one global lock, fine for one demo process
        self._lock = threading.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))

    def append(self, result: dict) -> dict:
        """Stamp a copy of ``result`` with ``id`` and ``created_at``, then store it."""
        record = copy.deepcopy(result)
        record["id"] = str(uuid.uuid4())
        with self._lock:
            record["created_at"] = self._next_created_at()
            self._events.append(record)
            overflow = len(self._events) - self._capacity
            if overflow > 0:
                del self._events[:overflow]
            return copy.deepcopy(record)

    def list_since(self, since: str | None) -> list[dict]:
        """Return stored events strictly after ``since``, or all if ``since`` is missing."""
        cutoff: datetime | None = None
        if since is not None and since.strip():
            cutoff = parse_since(since)
        with self._lock:
            if cutoff is None:
                selected = self._events
            else:
                selected = [
                    event
                    for event in self._events
                    if datetime.fromisoformat(event["created_at"]) > cutoff
                ]
            return copy.deepcopy(selected)

    def _next_created_at(self) -> str:
        # Caller holds self._lock.
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("event-store clock must return a timezone-aware UTC datetime")
        now = now.astimezone(UTC)
        if self._events:
            last = datetime.fromisoformat(self._events[-1]["created_at"])
            if now <= last:
                now = last + timedelta(microseconds=1)
        return now.isoformat()


def attach_event_store(app: Any, *, replace: bool = False) -> EventStore:
    """Return the store on ``app.state``, creating it from settings if needed.

    Lifespan calls this with ``replace=True`` so each process start (and
    each TestClient context) gets a fresh desk. Ingest routes and the
    events dependency call it without ``replace`` so a TestClient that
    did not run lifespan still has a store.
    """
    if not replace:
        store = getattr(app.state, "event_store", None)
        if isinstance(store, EventStore):
            return store
    with _attach_lock:
        if not replace:
            store = getattr(app.state, "event_store", None)
            if isinstance(store, EventStore):
                return store
        store = EventStore(capacity=get_settings().event_store_capacity)
        app.state.event_store = store
        return store
