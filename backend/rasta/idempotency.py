"""Idempotency-Key replay for credit-spending POSTs (issue 26)."""

from __future__ import annotations

import hashlib
import re
import threading

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gnani_client.env import api_key
from rasta.errors import error_json_response
from rasta.store import attach_event_store

IDEMPOTENCY_TTL_SECONDS = 10 * 60
# Same 2 MB file plus multipart framing allowance as issue 27's raw guard.
MAX_IDEMPOTENCY_REQUEST_BYTES = 2_000_000 + 64 * 1024


class IdempotencyBodyTooLarge(Exception):
    pass


IDEMPOTENCY_KEY_RE = re.compile(r"^[\w.-]{8,128}$")
IDEMPOTENCY_HEADER = b"idempotency-key"

_CREDIT_EXACT = frozenset(
    {
        "/api/ingest",
        "/api/ingest/sample",
        "/api/simulate",
        "/api/v1/ingest",
        "/api/v1/ingest/sample",
        "/api/v1/simulate",
    }
)
_REPLY = re.compile(r"^/api(?:/v1)?/reply/[^/]+$")


def is_credit_path(path: str) -> bool:
    return path in _CREDIT_EXACT or bool(_REPLY.match(path))


def canonical_route(path: str) -> str:
    if path.startswith("/api/v1/"):
        return "/api/" + path[len("/api/v1/") :]
    return path


def hash_token(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key == name:
            try:
                return value.decode("ascii").strip()
            except UnicodeDecodeError:
                return ""
    return None


class IdempotencyMiddleware:
    """Replay a stored response, or record a new one, for credit POSTs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._claim_lock = threading.Lock()
        self._pending: dict[tuple[object, str, str], str] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if not is_credit_path(path):
            await self.app(scope, receive, send)
            return
        raw_key = _header(scope, IDEMPOTENCY_HEADER)
        if raw_key is None:
            await self.app(scope, receive, send)
            return
        if not IDEMPOTENCY_KEY_RE.fullmatch(raw_key):
            response = error_json_response(
                400,
                "validation_error",
                "Idempotency-Key must be a UUID or an 8-128 character token.",
            )
            await response(scope, receive, send)
            return

        try:
            body, replay = await _buffer_body(receive)
        except IdempotencyBodyTooLarge:
            response = error_json_response(413, "payload_too_large", "Request body is too large.")
            await response(scope, receive, send)
            return
        except ClientDisconnect:
            return
        app = scope.get("app")
        if app is None:
            await self.app(scope, replay, send)
            return
        store = attach_event_store(app)
        route = canonical_route(path)
        key_hash = hash_token(raw_key.encode("ascii"))
        # Query string is part of the request identity so /sample?condition=
        # clean versus noisy with the same key is a conflict, not a silent replay.
        query = bytes(scope.get("query_string") or b"")
        body_hash = hash_token(query + b"\0" + body)
        claim = (store, key_hash, route)
        # No await separates lookup and claim. The lock also covers TestClient's
        # independent event-loop threads; one async lock would not cover those.
        with self._claim_lock:
            cached = store.lookup_idempotency(key_hash, route, body_hash)
            if cached is None:
                pending_hash = self._pending.get(claim)
                if pending_hash is None:
                    self._pending[claim] = body_hash
                else:
                    cached = "pending" if pending_hash == body_hash else "conflict"
        if cached == "unavailable":
            response = error_json_response(
                503,
                "idempotency_response_unavailable",
                "The stored response is unavailable. This key will not start paid work again.",
            )
            await response(scope, receive, send)
            return
        if cached == "pending":
            response = error_json_response(
                409,
                "idempotency_in_progress",
                "That request is still running. Reuse this key later.",
            )
            await response(scope, receive, send)
            return
        if cached == "conflict":
            response = error_json_response(
                409,
                "idempotency_conflict",
                "That Idempotency-Key was already used with a different body.",
            )
            await response(scope, receive, send)
            return
        if isinstance(cached, tuple):
            status, payload = cached
            if status < 400 and not api_key():
                response = error_json_response(503, "missing_api_key", "GNANI_API_KEY is not set")
                await response(scope, receive, send)
                return
            from starlette.responses import Response

            response = Response(
                content=payload,
                status_code=status,
                media_type="application/json",
            )
            await response(scope, receive, send)
            return

        start: dict | None = None
        chunks = bytearray()
        recorded = False

        async def capture(message: Message) -> None:
            nonlocal start, recorded
            if message["type"] == "http.response.start":
                start = {**message, "headers": list(message.get("headers") or [])}
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.extend(message.get("body") or b"")
            if message.get("more_body"):
                return
            assert start is not None
            status = int(start.get("status") or 200)
            store.remember_idempotency(key_hash, route, body_hash, status, bytes(chunks))
            recorded = True
            await send(start)
            await send({"type": "http.response.body", "body": bytes(chunks), "more_body": False})

        try:
            await self.app(scope, replay, capture)
        finally:
            try:
                if not recorded:
                    # Cancellation may leave paid work running under the resilience
                    # guard. Never let a duplicate start that uncertain work again.
                    uncertain = error_json_response(
                        503,
                        "idempotency_outcome_unknown",
                        "Original outcome unknown. This key will not start paid work again.",
                    )
                    store.remember_idempotency(key_hash, route, body_hash, 503, uncertain.body)
                    recorded = True
            finally:
                # If SQLite cannot record even the conservative outcome, retain
                # the in-memory claim rather than risk charging this key twice.
                if recorded:
                    with self._claim_lock:
                        self._pending.pop(claim, None)


async def _buffer_body(receive: Receive) -> tuple[bytes, Receive]:
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.request":
            chunk = message.get("body") or b""
            if len(chunk) > MAX_IDEMPOTENCY_REQUEST_BYTES - len(body):
                raise IdempotencyBodyTooLarge
            body.extend(chunk)
            if not message.get("more_body"):
                break
        elif message["type"] == "http.disconnect":
            raise ClientDisconnect
    payload = bytes(body)
    delivered = False

    async def replay() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return await receive()

    return payload, replay
