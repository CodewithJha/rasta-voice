"""Public-demo speech budget and per-IP caps (issue 13).

One process, one worker. Reservations are taken when a billable route is
admitted so two overlapping sample clicks cannot both spend. Concurrency
slots are released when the request or stream ends. Spent budget is not
refunded if the upstream call later fails.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from rasta.settings import Settings, get_settings

# Sample ingest is Timbre plus Prisma. A live stream session is one Prisma
# connection at accept. Reply generation is one Timbre call.
_SPEECH_COSTS = {
    ("POST", "/api/ingest/sample"): 2,
    ("POST", "/api/ingest"): 1,
    ("POST", "/api/simulate"): 1,
}

PAUSED = "Public speech is paused."
BUDGET = "The public speech budget is exhausted."
RATE = "Too many speech requests from this address. Try again in a minute."
BUSY = "The demo is at its speech concurrency limit. Try again in a moment."

_attach_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class Decision:
    status: int
    message: str


def speech_cost(method: str, path: str) -> int | None:
    """Return the reserved Gnani-call cost, or None if the route is free."""
    key = (method.upper(), path)
    if key in _SPEECH_COSTS:
        return _SPEECH_COSTS[key]
    if method.upper() == "POST" and path.startswith("/api/reply/"):
        return 1
    if path == "/api/stream" and method.upper() in {"GET", "WEBSOCKET"}:
        return 1
    return None


def client_ip(scope: Scope, settings: Settings) -> str:
    """Peer address, or the first X-Forwarded-For hop when trust is enabled."""
    if settings.trust_proxy_headers:
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        forwarded = headers.get("x-forwarded-for", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return "unknown"


class SpeechGuard:
    """In-process budget, per-IP window, and concurrency gate."""

    def __init__(self, settings: Settings, *, clock=time.monotonic) -> None:
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._spent: list[tuple[float, int]] = []
        self._ip: dict[str, list[float]] = {}
        self._inflight = 0

    def remaining(self) -> int:
        with self._lock:
            self._prune(self._clock())
            used = sum(calls for _at, calls in self._spent)
            return max(0, self._settings.demo_speech_budget - used)

    def admit(self, ip: str, calls: int, *, acquire_slot: bool = True) -> Decision | None:
        """Reserve ``calls`` and a concurrency slot, or return a rejection."""
        settings = self._settings
        if settings.demo_speech_budget <= 0:
            return Decision(503, PAUSED)
        with self._lock:
            now = self._clock()
            self._prune(now)
            used = sum(item for _at, item in self._spent)
            if used + calls > settings.demo_speech_budget:
                return Decision(503, BUDGET)
            window = [at for at in self._ip.get(ip, []) if now - at < 60.0]
            if len(window) >= settings.per_ip_requests_per_minute:
                self._ip[ip] = window
                return Decision(429, RATE)
            if acquire_slot and self._inflight >= settings.max_concurrent_speech:
                return Decision(503, BUSY)
            window.append(now)
            self._ip[ip] = window
            self._spent.append((now, calls))
            if acquire_slot:
                self._inflight += 1
            return None

    def release_slot(self) -> None:
        with self._lock:
            if self._inflight > 0:
                self._inflight -= 1

    def _prune(self, now: float) -> None:
        horizon = self._settings.demo_speech_window_seconds
        self._spent = [(at, calls) for at, calls in self._spent if now - at < horizon]
        self._ip = {
            ip: [at for at in stamps if now - at < 60.0]
            for ip, stamps in self._ip.items()
            if any(now - at < 60.0 for at in stamps)
        }


def attach_speech_guard(app: Any, *, replace: bool = False) -> SpeechGuard:
    """Return the process guard, creating it from settings if needed."""
    if not replace:
        guard = getattr(app.state, "speech_guard", None)
        if isinstance(guard, SpeechGuard):
            return guard
    with _attach_lock:
        if not replace:
            guard = getattr(app.state, "speech_guard", None)
            if isinstance(guard, SpeechGuard):
                return guard
        guard = SpeechGuard(get_settings())
        app.state.speech_guard = guard
        return guard


def admit_websocket(app: Any, scope: Scope) -> Decision | None:
    """Reserve a stream session or return the rejection to send after accept."""
    settings = get_settings()
    cost = speech_cost("WEBSOCKET", "/api/stream")
    assert cost is not None
    return attach_speech_guard(app).admit(
        client_ip(scope, settings), cost, acquire_slot=False
    )


class SpeechBudgetMiddleware:
    """ASGI wrapper so billable HTTP routes cannot bypass the cap."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cost = speech_cost(scope["method"], scope.get("path", ""))
        if cost is None:
            await self.app(scope, receive, send)
            return
        # Starlette Request needs the app on the scope (set by FastAPI).
        app = scope.get("app")
        if app is None:
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        decision = attach_speech_guard(app).admit(client_ip(scope, settings), cost)
        if decision is not None:
            from starlette.responses import JSONResponse

            response = JSONResponse({"detail": decision.message}, status_code=decision.status)
            await response(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            attach_speech_guard(app).release_slot()


def request_client_ip(request: Request) -> str:
    return client_ip(request.scope, get_settings())
