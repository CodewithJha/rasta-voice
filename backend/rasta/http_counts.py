"""In-process 4xx/5xx counters for the desk usage strip (issue 25)."""

from __future__ import annotations

import threading
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send


class HttpCounts:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.client_errors = 0
        self.server_errors = 0

    def record(self, status: int) -> None:
        if status < 400:
            return
        with self._lock:
            if status >= 500:
                self.server_errors += 1
            else:
                self.client_errors += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "4xx": self.client_errors,
                "5xx": self.server_errors,
            }


def attach_http_counts(app: Any, *, replace: bool = False) -> HttpCounts:
    existing = getattr(getattr(app, "state", None), "http_counts", None)
    if isinstance(existing, HttpCounts) and not replace:
        return existing
    counts = HttpCounts()
    app.state.http_counts = counts
    return counts


class HttpCountMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def inner(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                counts = scope.get("app")
                state = getattr(counts, "state", None) if counts is not None else None
                tracker = getattr(state, "http_counts", None)
                status = message.get("status")
                if tracker is not None and isinstance(status, int):
                    tracker.record(status)
            await send(message)

        await self.app(scope, receive, inner)
