"""Idempotency-Key replay for credit-spending POSTs (issue 26)."""

from __future__ import annotations

import hashlib
import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rasta.errors import error_json_response
from rasta.store import attach_event_store

IDEMPOTENCY_TTL_SECONDS = 10 * 60
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

        body, replay = await _buffer_body(receive)
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
        cached = store.lookup_idempotency(key_hash, route, body_hash)
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

        async def capture(message: Message) -> None:
            nonlocal start
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
            await send(start)
            await send({"type": "http.response.body", "body": bytes(chunks), "more_body": False})

        await self.app(scope, replay, capture)


async def _buffer_body(receive: Receive) -> tuple[bytes, Receive]:
    messages: list[Message] = []
    body = bytearray()
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] == "http.request":
            body.extend(message.get("body") or b"")
            if not message.get("more_body"):
                break
        elif message["type"] == "http.disconnect":
            break

    async def replay() -> Message:
        if messages:
            return messages.pop(0)
        return await receive()

    return bytes(body), replay
