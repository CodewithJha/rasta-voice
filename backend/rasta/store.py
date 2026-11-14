"""SQLite dispatch event store (issue 19).

The public ``append`` / ``list_since`` shape is unchanged from issue 04:
stamped ``id`` and ``created_at``, cap applied on append, unknown envelope
keys kept. The running app always opens the file at ``RASTA_DB_PATH``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import secrets
import sqlite3
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from rasta.request_id import current_request_id
from rasta.settings import get_settings

# One lock for installing the process-wide store onto app.state.
_attach_lock = threading.Lock()
IDEMPOTENCY_RESPONSE_ENTRIES = 128
IDEMPOTENCY_RESPONSE_BYTES = 8 * 1024 * 1024
log = logging.getLogger("rasta")

# Current schema. Version 1 is an events table only (id, created_at, payload).
# Version 2 adds the schema_version table and the created_at index.
# Version 3 adds the audit table for desk workflow (issue 25).
# Version 4 adds the hashed idempotency table (issue 26).
CURRENT_SCHEMA_VERSION = 4
BUSY_TIMEOUT_MS = 3000
RIDER_ID_RE = re.compile(r"^r_[A-Za-z0-9_-]{1,32}$")
ACTOR_RE = re.compile(r"^d_[A-Za-z0-9_-]{1,32}$")
WORKFLOW_STATES = ("new", "acked", "resolved", "escalated")
_rider_override: ContextVar[str | None] = ContextVar("rasta_rider_id", default=None)


class EventNotFound(KeyError):
    """No event exists for the requested id."""


class VersionConflict(Exception):
    """If-Match did not equal the stored version."""

    def __init__(self, version: int) -> None:
        super().__init__("desk changed, try again")
        self.version = version
        self.code = "version_conflict"


class IllegalTransition(Exception):
    """The requested action is not allowed from the current state."""

    def __init__(self, state: str, action: str) -> None:
        super().__init__(f"cannot {action} a {state} event")
        self.state = state
        self.action = action
        self.code = "illegal_transition"


def mint_rider_id() -> str:
    return "r_" + secrets.token_hex(8)


def normalize_rider_id(raw: str | None) -> str:
    text = (raw or "").strip()
    if RIDER_ID_RE.fullmatch(text):
        return text
    return mint_rider_id()


def bind_rider_header(raw: str | None):
    return _rider_override.set(normalize_rider_id(raw) if (raw or "").strip() else None)


def reset_rider_header(token) -> None:
    _rider_override.reset(token)


def normalize_actor(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if ACTOR_RE.fullmatch(text):
        return text
    return None


def parse_if_match(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    if not text.isdigit():
        return None
    return int(text)


def _stamp_new_envelope(record: dict) -> None:
    """Fill default desk-lifecycle fields without overwriting caller values."""
    record.setdefault("state", "new")
    record.setdefault("version", 1)
    override = _rider_override.get()
    existing = record.get("rider_id")
    if not isinstance(existing, str) or not RIDER_ID_RE.fullmatch(existing):
        record["rider_id"] = override or mint_rider_id()
    record.setdefault("ack_by", None)
    record.setdefault("ack_at", None)
    record.setdefault("resolved_by", None)
    record.setdefault("resolved_at", None)
    record.setdefault("escalated_at", None)


def _apply_transition(
    record: dict,
    *,
    action: str,
    actor: str,
    at: str,
    also_ack: bool = False,
) -> None:
    state = record.get("state") or "new"
    if action == "ack":
        if state not in {"new", "escalated"}:
            raise IllegalTransition(state, action)
        record["state"] = "acked"
        record["ack_by"] = actor
        record["ack_at"] = at
    elif action == "escalate":
        if state not in {"new", "acked"}:
            raise IllegalTransition(state, action)
        record["state"] = "escalated"
        record["escalated_at"] = at
    elif action == "resolve":
        already_acked = bool(record.get("ack_at") or record.get("ack_by"))
        if state == "acked" or (state == "escalated" and (already_acked or also_ack)):
            if also_ack and not already_acked:
                record["ack_by"] = actor
                record["ack_at"] = at
            record["state"] = "resolved"
            record["resolved_by"] = actor
            record["resolved_at"] = at
        else:
            raise IllegalTransition(state, action)
    else:
        raise IllegalTransition(state, action)
    record["version"] = int(record.get("version") or 1) + 1


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
        connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS events_created_at_idx ON events (created_at)"
        )
        _write_schema_version(connection, 2)
        version = 2
    if version < 3:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit (
                at TEXT NOT NULL,
                event_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                request_id TEXT,
                detail TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS audit_event_id_at_idx ON audit (event_id, at)"
        )
        _write_schema_version(connection, 3)
        version = 3
    if version < 4:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                key_hash TEXT NOT NULL,
                route TEXT NOT NULL,
                body_hash TEXT NOT NULL,
                status INTEGER NOT NULL,
                response TEXT NOT NULL,
                stored_at TEXT NOT NULL,
                PRIMARY KEY (key_hash, route)
            )
            """
        )
        _write_schema_version(connection, CURRENT_SCHEMA_VERSION)
        version = CURRENT_SCHEMA_VERSION
    connection.commit()


def _write_schema_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    connection.execute("DELETE FROM schema_version")
    connection.execute(
        "INSERT INTO schema_version (version) VALUES (?)",
        (version,),
    )


def _schema_version(connection: sqlite3.Connection) -> int:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchall()
    if not rows:
        events = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'events'"
        ).fetchall()
        return 1 if events else 0
    row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
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
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be a positive integer")
        if not path:
            raise ValueError("path is required")
        self._capacity = capacity
        self._path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # One lock around write + trim, fine for one demo process.
        self._lock = threading.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._idempotency_responses: OrderedDict[
            tuple[str, str], tuple[datetime, int, bytes, str | None]
        ] = OrderedDict()
        self._idempotency_response_bytes = 0
        self._conn = _connect(path)
        self._closed = False
        migrate(self._conn)
        self._last_change = self._max_change_stamp_unlocked()

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
            self._idempotency_responses.clear()
            self._idempotency_response_bytes = 0
            self._conn.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            return

    def append(self, result: dict) -> dict:
        """Stamp a copy of ``result`` with ``id`` and ``created_at``, then store it."""
        record = copy.deepcopy(result)
        record["id"] = str(uuid.uuid4())
        _stamp_new_envelope(record)
        with self._lock:
            record["created_at"] = self._next_created_at()
            if "updated_at" not in record or not record["updated_at"]:
                record["updated_at"] = self._next_change_stamp(
                    datetime.fromisoformat(record["created_at"])
                )
            else:
                record["updated_at"] = self._later_stamp(record, str(record["updated_at"]))
            self._conn.execute(
                "INSERT INTO events (id, created_at, payload) VALUES (?, ?, ?)",
                (record["id"], record["created_at"], json.dumps(record)),
            )
            self._audit_locked(
                record["created_at"],
                record["id"],
                str(record.get("rider_id") or "r_unknown"),
                "ingest",
                {"state": record.get("state"), "version": record.get("version")},
            )
            self._trim_locked()
            self._conn.commit()
            return copy.deepcopy(record)

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
            events = [json.loads(row[0]) for row in rows]
        if cutoff is not None:
            events = [
                event for event in events if datetime.fromisoformat(event["created_at"]) > cutoff
            ]
        return copy.deepcopy(events)

    def list_updated_since(self, since: str | None) -> list[dict]:
        """Return rows created or updated after ``since``, in creation order."""
        events = self.list_since(None)
        if since is None or (isinstance(since, str) and not since.strip()):
            return events
        cutoff = parse_since(since)
        changed = []
        for event in events:
            stamp = event.get("updated_at") or event.get("created_at")
            when = datetime.fromisoformat(str(stamp))
            if when.tzinfo is None:
                continue
            if when.astimezone(UTC) > cutoff:
                changed.append(event)
        return changed

    def get(self, event_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        return copy.deepcopy(json.loads(row[0]))

    def list_audit(self, event_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT at, event_id, actor, action, request_id, detail "
                "FROM audit WHERE event_id = ? ORDER BY at ASC",
                (event_id,),
            ).fetchall()
        events = []
        for row in rows:
            item = {
                "at": row[0],
                "event_id": row[1],
                "actor": row[2],
                "action": row[3],
                "request_id": row[4],
                "detail": json.loads(row[5]),
            }
            events.append(item)
        return events

    def _forget_idempotency_response_locked(self, key: tuple[str, str]) -> None:
        entry = self._idempotency_responses.pop(key, None)
        if entry is not None:
            self._idempotency_response_bytes -= len(entry[2])

    def _trim_idempotency_responses_locked(self, now: datetime) -> None:
        for key, entry in list(self._idempotency_responses.items()):
            if entry[0] <= now:
                self._forget_idempotency_response_locked(key)
        while (
            len(self._idempotency_responses) > IDEMPOTENCY_RESPONSE_ENTRIES
            or self._idempotency_response_bytes > IDEMPOTENCY_RESPONSE_BYTES
        ):
            self._forget_idempotency_response_locked(next(iter(self._idempotency_responses)))

    def _idempotency_event_live_locked(self, event_id: str | None, now: datetime) -> bool:
        if event_id is None:
            return True
        row = self._conn.execute("SELECT payload FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return False
        # Privacy's TTL implementation owns expiry. Its merge must not allow a
        # still-cached pre-expiry response to outlive the referenced event.
        expired = getattr(self, "_is_expired", None)
        return not (callable(expired) and expired(json.loads(row[0]), now))

    def lookup_idempotency(
        self, key_hash: str, route: str, body_hash: str
    ) -> tuple[int, bytes] | str | None:
        """Read metadata plus bounded memory response; never restart a lost replay."""
        from rasta.idempotency import IDEMPOTENCY_TTL_SECONDS

        now = self._clock().astimezone(UTC)
        cutoff = (now - timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)).isoformat()
        key = (key_hash, route)
        with self._lock:
            self._trim_idempotency_responses_locked(now)
            self._conn.execute("DELETE FROM idempotency WHERE stored_at <= ?", (cutoff,))
            row = self._conn.execute(
                "SELECT body_hash FROM idempotency WHERE key_hash = ? AND route = ?",
                (key_hash, hashlib.sha256(route.encode()).hexdigest()),
            ).fetchone()
            self._conn.commit()
            if row is None:
                self._forget_idempotency_response_locked(key)
                return None
            if str(row[0]) != body_hash:
                return "conflict"
            cached = self._idempotency_responses.get(key)
            if cached is None:
                return "unavailable"
            if not self._idempotency_event_live_locked(cached[3], now):
                self._forget_idempotency_response_locked(key)
                return "unavailable"
            self._idempotency_responses.move_to_end(key)
            return cached[1], cached[2]

    def remember_idempotency(
        self,
        key_hash: str,
        route: str,
        body_hash: str,
        status: int,
        response: bytes,
    ) -> None:
        from rasta.idempotency import IDEMPOTENCY_TTL_SECONDS

        now = self._clock().astimezone(UTC)
        cutoff = (now - timedelta(seconds=IDEMPOTENCY_TTL_SECONDS)).isoformat()
        event_id = (
            route.rsplit("/", 1)[-1] if status < 400 and route.startswith("/api/reply/") else None
        )
        try:
            payload = json.loads(response)
            if status < 400 and isinstance(payload, dict):
                ingest = payload.get("ingest", payload)
                if isinstance(ingest, dict) and isinstance(ingest.get("id"), str):
                    event_id = ingest["id"]
        except (ValueError, UnicodeDecodeError):
            pass
        key = (key_hash, route)
        with self._lock:
            self._conn.execute("DELETE FROM idempotency WHERE stored_at <= ?", (cutoff,))
            # Speech text and base64 audio never enter the persistent replay table.
            # An empty body is a retained claim, not permission to run work again.
            self._conn.execute(
                "INSERT OR REPLACE INTO idempotency "
                "(key_hash, route, body_hash, status, response, stored_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    key_hash,
                    hashlib.sha256(route.encode()).hexdigest(),
                    body_hash,
                    int(status),
                    "",
                    now.isoformat(),
                ),
            )
            self._conn.commit()
            self._forget_idempotency_response_locked(key)
            self._idempotency_responses[key] = (
                now + timedelta(seconds=IDEMPOTENCY_TTL_SECONDS),
                int(status),
                response,
                event_id,
            )
            self._idempotency_response_bytes += len(response)
            self._trim_idempotency_responses_locked(now)

    def counts_by_state(self) -> dict[str, int]:
        counts = {state: 0 for state in WORKFLOW_STATES}
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM events").fetchall()
        for row in rows:
            record = json.loads(row[0])
            state = record.get("state") or "new"
            if state not in counts:
                counts[state] = 0
            counts[state] += 1
        return counts

    def sos_unacked(self) -> int:
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM events").fetchall()
        total = 0
        for row in rows:
            record = json.loads(row[0])
            event = record.get("event") or {}
            state = record.get("state") or "new"
            if event.get("intent") == "accident_sos" and state in {"new", "escalated"}:
                total += 1
        return total

    def transition(
        self,
        event_id: str,
        *,
        action: str,
        actor: str,
        if_match: int,
        also_ack: bool = False,
    ) -> dict:
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("event-store clock must return a timezone-aware UTC datetime")
        stamp = now.astimezone(UTC).isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                raise EventNotFound(event_id)
            record = json.loads(row[0])
            version = int(record.get("version") or 1)
            if if_match != version:
                raise VersionConflict(version)
            _apply_transition(record, action=action, actor=actor, at=stamp, also_ack=also_ack)
            record["updated_at"] = self._later_stamp(record, stamp)
            self._conn.execute(
                "UPDATE events SET payload = ? WHERE id = ?",
                (json.dumps(record), event_id),
            )
            self._audit_locked(
                stamp,
                event_id,
                actor,
                action,
                {"state": record.get("state"), "version": record.get("version")},
            )
            self._conn.commit()
            return copy.deepcopy(record)

    def escalate_overdue(self, timeout_seconds: float) -> int:
        """Auto-escalate unacked accident_sos rows older than ``timeout_seconds``."""
        now = self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("event-store clock must return a timezone-aware UTC datetime")
        now = now.astimezone(UTC)
        updated = 0
        with self._lock:
            rows = self._conn.execute("SELECT id, created_at, payload FROM events").fetchall()
            for row in rows:
                record = json.loads(row[2])
                event = record.get("event") or {}
                state = record.get("state") or "new"
                if event.get("intent") != "accident_sos" or state != "new":
                    continue
                created = datetime.fromisoformat(record.get("created_at") or row[1])
                if created.tzinfo is None:
                    continue
                age = (now - created.astimezone(UTC)).total_seconds()
                if age < timeout_seconds:
                    continue
                stamp = now.isoformat()
                version = int(record.get("version") or 1)
                _apply_transition(
                    record, action="escalate", actor="d_system", at=stamp, also_ack=False
                )
                record["updated_at"] = self._later_stamp(record, stamp)
                self._conn.execute(
                    "UPDATE events SET payload = ? WHERE id = ?",
                    (json.dumps(record), row[0]),
                )
                self._audit_locked(
                    stamp,
                    row[0],
                    "d_system",
                    "escalate",
                    {
                        "state": record.get("state"),
                        "version": record.get("version"),
                        "reason": "sos_timeout",
                        "from_version": version,
                    },
                )
                updated += 1
            if updated:
                self._conn.commit()
        return updated

    def _audit_locked(
        self,
        at: str,
        event_id: str,
        actor: str,
        action: str,
        detail: dict[str, Any],
    ) -> None:
        self._conn.execute(
            "INSERT INTO audit (at, event_id, actor, action, request_id, detail) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                at,
                event_id,
                actor,
                action,
                current_request_id(),
                json.dumps(detail),
            ),
        )

    def export_copy(self, dest: str | Path) -> None:
        """Write a consistent SQLite copy to ``dest``."""
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists():
            dest_path.unlink()
        target = sqlite3.connect(dest_path)
        try:
            with self._lock:
                self._conn.backup(target)
        finally:
            target.close()

    def _trim_locked(self) -> None:
        # Caller holds self._lock.
        row = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()
        overflow = int(row[0]) - self._capacity
        if overflow <= 0:
            return
        # Until issue 28 lands, evict the oldest rows and log only id and
        # created_at so a live SOS is not specially protected yet, and
        # transcripts are not written to the log.
        stale = self._conn.execute(
            "SELECT id, created_at FROM events ORDER BY created_at ASC, id ASC LIMIT ?",
            (overflow,),
        ).fetchall()
        for item in stale:
            self._conn.execute("DELETE FROM events WHERE id = ?", (item[0],))
            log.info(
                "event store evicted id=%s created_at=%s",
                item[0],
                item[1],
            )

    def _max_change_stamp_unlocked(self) -> datetime | None:
        """Latest published created_at/updated_at. Caller may already hold the lock."""
        latest: datetime | None = None
        rows = self._conn.execute("SELECT payload FROM events").fetchall()
        for row in rows:
            record = json.loads(row[0])
            for key in ("updated_at", "created_at"):
                raw = record.get(key)
                if not raw:
                    continue
                try:
                    when = datetime.fromisoformat(str(raw))
                except ValueError:
                    continue
                if when.tzinfo is None:
                    continue
                when = when.astimezone(UTC)
                if latest is None or when > latest:
                    latest = when
        return latest

    def _next_change_stamp(self, suggested: datetime | None = None) -> str:
        """Allocate a stamp strictly after every published change. Caller holds the lock."""
        now = suggested if suggested is not None else self._clock()
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            raise ValueError("event-store clock must return a timezone-aware UTC datetime")
        now = now.astimezone(UTC)
        last = self._last_change
        if last is not None and now <= last:
            now = last + timedelta(microseconds=1)
        self._last_change = now
        return now.isoformat()

    def _later_stamp(self, record: dict, stamp: str) -> str:
        when = datetime.fromisoformat(stamp)
        if when.tzinfo is None:
            return self._next_change_stamp()
        return self._next_change_stamp(when.astimezone(UTC) if when.tzinfo else when)

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
        store = EventStore(capacity=settings.event_store_capacity, path=settings.db_path)
        app.state.event_store = store
        if previous is not None and previous is not store:
            previous.close()
        return store
