"""SQLite dispatch event store (issue 19).

The public ``append`` / ``list_since`` shape is unchanged from issue 04:
stamped ``id`` and ``created_at``, cap applied on append, unknown envelope
keys kept. The running app always opens the file at ``RASTA_DB_PATH``.
"""

from __future__ import annotations

import copy
import json
import logging
import sqlite3
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rasta.redact import redact_record
from rasta.settings import DEFAULT_EVENT_TTL_HOURS, get_settings

# One lock for installing the process-wide store onto app.state.
_attach_lock = threading.Lock()
log = logging.getLogger("rasta")

# Current schema. Version 1 is an events table only (id, created_at, payload).
# Version 2 adds the schema_version table and the created_at index.
CURRENT_SCHEMA_VERSION = 2
RESOLVED_STATE = "resolved"
ACCIDENT_SOS_INTENT = "accident_sos"
WIPE_CONFIRM = "wipe"
BUSY_TIMEOUT_MS = 3000

# ISO 8601 instants with a numeric offset are well under this length.
# Longer input is rejected up front so the parser stays bounded.
_SINCE_MAX_LENGTH = 64
_SINCE_ERROR = "since must be a timezone-aware UTC ISO 8601 timestamp"


class InvalidSince(ValueError):
    """Raised when ``list_since`` cannot parse or cannot use ``since``."""


def parse_since(since: object) -> datetime:
    """Parse a tz-aware ISO 8601 timestamp into an aware UTC datetime.

    This is a total function: it returns an aware UTC ``datetime`` or
    raises ``InvalidSince``. A trailing ``Z`` or ``z`` is accepted as
    UTC. Naive values, malformed strings, non-strings, overly long
    input, and timestamps that cannot be normalized to UTC (for
    example year-0001 / year-9999 overflow) all raise ``InvalidSince``
    so the router can answer 422.
    """
    if not isinstance(since, str) or len(since) > _SINCE_MAX_LENGTH:
        raise InvalidSince(_SINCE_ERROR)
    text = since.strip()
    if not text:
        raise InvalidSince(_SINCE_ERROR)
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(text)
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise InvalidSince(_SINCE_ERROR)
        return value.astimezone(UTC)
    except InvalidSince:
        raise
    except (ValueError, OverflowError, OSError, TypeError) as exc:
        raise InvalidSince(_SINCE_ERROR) from exc


def _connect(path: str) -> sqlite3.Connection:
    # check_same_thread is off because ingest runs in a worker thread; all
    # access still goes through the store lock. One writer process.
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    if path != ":memory:":
        # WAL is safe here because this demo still has a single writer
        # process; it is not a multi-process server.
        connection.execute("PRAGMA journal_mode=WAL")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    """Bring an on-disk (or memory) database up to ``CURRENT_SCHEMA_VERSION``."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    version = _schema_version(connection)
    if version < 2:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS events_created_at_idx ON events (created_at)"
        )
        connection.execute("DELETE FROM schema_version")
        connection.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (CURRENT_SCHEMA_VERSION,),
        )
        connection.commit()


def _schema_version(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchall()
    if not rows:
        events = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'events'"
        ).fetchall()
        return 1 if events else 0
    row = connection.execute(
        "SELECT version FROM schema_version LIMIT 1"
    ).fetchone()
    if row is None:
        return 1
    return int(row[0])


class EventStore:
    """Append-only ring of recent ingest records, oldest first.

    Capacity is injected (from settings). ``append`` and ``list_since``
    copy on the way in and out so callers cannot alias stored dicts.
    ``created_at`` is UTC ISO 8601 and strictly monotonic in this process
    so a ``?since=<last created_at>`` poll cannot miss a later append.

    ``path=":memory:"`` is for tests only. The running app always passes
    the file path from Settings.
    """

    def __init__(
        self,
        capacity: int,
        path: str,
        *,
        clock: Callable[[], datetime] | None = None,
        ttl_hours: int | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be a positive integer")
        if not path:
            raise ValueError("path is required")
        if ttl_hours is None:
            ttl_hours = DEFAULT_EVENT_TTL_HOURS
        if ttl_hours < 0:
            raise ValueError("ttl_hours must be >= 0")
        self._capacity = capacity
        self._path = path
        self._ttl_hours = ttl_hours
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One lock around write + trim, fine for one demo process.
        self._lock = threading.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._conn = _connect(path)
        self._closed = False
        migrate(self._conn)
        with self._lock:
            self._redact_existing_locked()
            self._conn.commit()

    @property
    def path(self) -> str:
        return self._path

    def schema_version(self) -> int:
        with self._lock:
            return _schema_version(self._conn)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            return

    def append(self, result: dict) -> dict:
        """Stamp a copy of ``result`` with ``id`` and ``created_at``, then store it."""
        record = redact_record(copy.deepcopy(result))
        record["id"] = str(uuid.uuid4())
        with self._lock:
            record["created_at"] = self._next_created_at()
            self._conn.execute(
                "INSERT INTO events (id, created_at, payload) VALUES (?, ?, ?)",
                (record["id"], record["created_at"], json.dumps(record)),
            )
            self._trim_locked()
            self._conn.commit()
            return redact_record(copy.deepcopy(record))

    def list_since(self, since: str | None) -> list[dict]:
        """Return stored events strictly after ``since``, or all if ``since`` is missing."""
        cutoff: datetime | None = None
        if since is None or (isinstance(since, str) and not since.strip()):
            cutoff = None
        else:
            cutoff = parse_since(since)
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM events ORDER BY created_at ASC, id ASC"
            ).fetchall()
            now = self._clock()
            events = []
            for row in rows:
                event = json.loads(row[0])
                if not self._is_expired(event, now):
                    events.append(event)
        if cutoff is not None:
            events = [
                event
                for event in events
                if datetime.fromisoformat(event["created_at"]) > cutoff
            ]
        return [redact_record(copy.deepcopy(event)) for event in events]

    def export_copy(self, dest: str | Path) -> None:
        """Write a consistent SQLite copy to ``dest``."""
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists():
            dest_path.unlink()
        target = sqlite3.connect(dest_path)
        try:
            with self._lock:
                now = self._clock()
                self._conn.backup(target)
                self._drop_expired_from_connection(target, now)
                self._redact_connection(target)
                target.commit()
        finally:
            target.close()

    def delete(self, event_id: str) -> bool:
        """Remove one event. Returns False when the id is not present."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if row is None:
                return False
            self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            self._conn.commit()
        log.info("event store deleted id=%s action=delete", event_id)
        return True

    def wipe(self) -> int:
        """Delete every event row. Usage counters are out of band and stay."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
            count = int(row[0])
            ids = [
                item[0]
                for item in self._conn.execute("SELECT id FROM events").fetchall()
            ]
            self._conn.execute("DELETE FROM events")
            self._conn.commit()
        log.info(
            "event store wiped count=%s action=wipe ids=%s",
            count,
            ",".join(ids),
        )
        return count

    def purge_expired(self) -> list[str]:
        """Delete rows past the TTL. Returns the removed event ids."""
        with self._lock:
            now = self._clock()
            rows = self._conn.execute(
                "SELECT id, created_at, payload FROM events"
            ).fetchall()
            expired: list[tuple[str, str]] = []
            for row in rows:
                record = json.loads(row[2])
                if self._is_expired(record, now):
                    expired.append((row[0], row[1]))
            for event_id, _created in expired:
                self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            if expired:
                self._conn.commit()
        ids = [item[0] for item in expired]
        if ids:
            log.info(
                "event store ttl purged count=%s action=ttl_purge ids=%s",
                len(ids),
                ",".join(ids),
            )
        return ids

    def get(self, event_id: str) -> dict | None:
        """Return one redacted event, or None if missing or expired."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM events WHERE id = ?", (event_id,)
            ).fetchone()
            if row is None:
                return None
            record = json.loads(row[0])
            if self._is_expired(record, self._clock()):
                return None
        return redact_record(copy.deepcopy(record))

    def _is_expired(self, record: dict, now: datetime) -> bool:
        raw = record.get("created_at")
        if not raw:
            return False
        try:
            created = datetime.fromisoformat(str(raw))
        except ValueError:
            return False
        if created.tzinfo is None or created.tzinfo.utcoffset(created) is None:
            return False
        created = created.astimezone(UTC)
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            now = now.replace(tzinfo=UTC)
        else:
            now = now.astimezone(UTC)
        return created + timedelta(hours=self._ttl_hours) <= now

    def _is_resolved(self, record: dict) -> bool:
        return record.get("state") == RESOLVED_STATE

    def _is_live_sos(self, record: dict) -> bool:
        event = record.get("event")
        intent = event.get("intent") if isinstance(event, dict) else None
        if intent != ACCIDENT_SOS_INTENT:
            return False
        return not self._is_resolved(record)

    def _redact_existing_locked(self) -> None:
        rows = self._conn.execute("SELECT id, payload FROM events").fetchall()
        for row in rows:
            record = json.loads(row[1])
            redacted = redact_record(record)
            if redacted != record:
                self._conn.execute(
                    "UPDATE events SET payload = ? WHERE id = ?",
                    (json.dumps(redacted), row[0]),
                )

    def _drop_expired_from_connection(
        self, connection: sqlite3.Connection, now: datetime
    ) -> None:
        rows = connection.execute("SELECT id, payload FROM events").fetchall()
        for row in rows:
            if self._is_expired(json.loads(row[1]), now):
                connection.execute("DELETE FROM events WHERE id = ?", (row[0],))

    def _redact_connection(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("SELECT id, payload FROM events").fetchall()
        for row in rows:
            record = json.loads(row[1])
            connection.execute(
                "UPDATE events SET payload = ? WHERE id = ?",
                (json.dumps(redact_record(record)), row[0]),
            )

    def _trim_locked(self) -> None:
        # Caller holds self._lock.
        row = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        overflow = int(row[0]) - self._capacity
        if overflow <= 0:
            return
        rows = self._conn.execute(
            "SELECT id, created_at, payload FROM events"
        ).fetchall()
        records = [
            (item[0], item[1], json.loads(item[2])) for item in rows
        ]

        def sort_key(item: tuple[str, str, dict]) -> tuple[str, str]:
            return (item[1], item[0])

        resolved = [item for item in records if self._is_resolved(item[2])]
        others = [item for item in records if not self._is_resolved(item[2])]
        stale = sorted(resolved, key=sort_key) + sorted(others, key=sort_key)
        for event_id, created_at, record in stale[:overflow]:
            self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            if self._is_live_sos(record):
                log.info(
                    "event store evicted id=%s created_at=%s action=evicted intent=%s",
                    event_id,
                    created_at,
                    ACCIDENT_SOS_INTENT,
                )
            else:
                log.info(
                    "event store evicted id=%s created_at=%s",
                    event_id,
                    created_at,
                )

    def _next_created_at(self) -> str:
        # Caller holds self._lock.
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("event-store clock must return a timezone-aware UTC datetime")
        now = now.astimezone(UTC)
        row = self._conn.execute(
            "SELECT created_at FROM events ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if row is not None:
            last = datetime.fromisoformat(row[0])
            if now <= last:
                now = last + timedelta(microseconds=1)
        return now.isoformat()


def attach_event_store(app: Any, *, replace: bool = False) -> EventStore:
    """Return the store on ``app.state``, creating it from settings if needed.

    Lifespan calls this with ``replace=True`` so a new process opens a
    fresh connection to the same file. Ingest routes and the events
    dependency call it without ``replace`` so a TestClient that did not
    run lifespan still has a store.
    """
    if not replace:
        store = getattr(app.state, "event_store", None)
        if isinstance(store, EventStore) and not store.closed:
            return store
    with _attach_lock:
        if not replace:
            store = getattr(app.state, "event_store", None)
            if isinstance(store, EventStore) and not store.closed:
                return store
        previous = getattr(app.state, "event_store", None)
        settings = get_settings()
        store = EventStore(
            capacity=settings.event_store_capacity,
            path=settings.db_path,
            ttl_hours=settings.event_ttl_hours,
        )
        app.state.event_store = store
        if previous is not None and previous is not store:
            previous.close()
        return store
