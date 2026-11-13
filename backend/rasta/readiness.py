"""Readiness snapshots for /api/ready (issue 22).

Issue 13's speech guard and issue 19's SQLite store are read from the
objects already attached on the app. Missing issue 29 breaker state is
reported as ``not_deployed`` rather than inventing a fake breaker.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Literal

from rasta.settings import get_settings

NOT_DEPLOYED: Literal["not_deployed"] = "not_deployed"

# JSON field type: a real value, or the honest "not yet shipped" marker.
ReadyValue = Any


def configured_db_path() -> Path | None:
    """Return the issue 19 store path if Settings already exposes one."""
    path = getattr(get_settings(), "db_path", None)
    if path is None or path == "":
        return None
    return Path(path)


def check_db_writable() -> bool | Literal["not_deployed"]:
    """Probe the durable store path. No path means issue 19 has not landed."""
    path = configured_db_path()
    if path is None:
        return NOT_DEPLOYED
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return False
    return True


def limiter_fields(app: Any) -> tuple[ReadyValue, ReadyValue, ReadyValue]:
    """Return remaining credits, exhausted flag, and rate-limit state.

    Reads issue 13's process guard when it is already attached. Does not
    construct a SpeechGuard, so this file cannot invent a budget on its own.
    """
    guard = getattr(app.state, "speech_guard", None)
    remaining_fn = getattr(guard, "remaining", None)
    if guard is None or not callable(remaining_fn):
        return NOT_DEPLOYED, NOT_DEPLOYED, NOT_DEPLOYED
    remaining = remaining_fn()
    if not isinstance(remaining, int) or isinstance(remaining, bool):
        return NOT_DEPLOYED, NOT_DEPLOYED, NOT_DEPLOYED
    remaining = max(0, remaining)
    cap = getattr(get_settings(), "per_ip_requests_per_minute", None)
    rate_limit: dict[str, Any] = {"ok": True}
    if isinstance(cap, int) and not isinstance(cap, bool) and cap >= 0:
        rate_limit["per_ip_requests_per_minute"] = cap
    return remaining, remaining <= 0, rate_limit


def _live_store(app: Any) -> Any | None:
    """Return the process store, or None if it cannot be opened."""
    store = getattr(app.state, "event_store", None)
    if store is not None and not getattr(store, "closed", False):
        return store
    try:
        from rasta.store import attach_event_store

        return attach_event_store(app)
    except Exception:
        return None


def events_in_store(app: Any) -> tuple[ReadyValue, bool]:
    """Count stored events. The boolean is False when the store cannot be read."""
    store = _live_store(app)
    if store is None:
        return None, False
    try:
        return len(store.list_since(None)), True
    except Exception:
        return None, False


def schema_version(app: Any) -> tuple[ReadyValue, bool]:
    """Read EventStore.schema_version(). False when the store cannot be queried."""
    store = _live_store(app)
    if store is None:
        return None, False
    try:
        return store.schema_version(), True
    except Exception:
        return None, False


def circuit_breaker(app: Any) -> ReadyValue:
    state = getattr(app.state, "circuit_breaker", None)
    if state is None:
        return NOT_DEPLOYED
    return state
