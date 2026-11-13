"""Shared dispatcher passcode for desk routes (issue 20).

Rider routes stay public. Desk reads need a valid session cookie or the
``X-Dispatch-Passcode`` header. Desk writes also need a CSRF token when
the caller authenticated with the cookie; a passcode header is enough
on its own because a cross-site form cannot set it.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response

from rasta.settings import Settings, get_settings

COOKIE_SESSION = "rasta_desk"
COOKIE_CSRF = "rasta_desk_csrf"
HEADER_PASSCODE = "X-Dispatch-Passcode"
HEADER_CSRF = "X-Dispatch-CSRF"

_ACTOR_RE = re.compile(r"^d_[0-9a-f]{16}$")
class UnlockLimiter:
    """In-process sliding window of failed unlocks, keyed by client address."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def _prune(self, address: str, now: float, window: float) -> list[float]:
        kept = [stamp for stamp in self._failures.get(address, []) if now - stamp < window]
        if kept:
            self._failures[address] = kept
        else:
            self._failures.pop(address, None)
        return kept

    def blocked(self, address: str, settings: Settings, *, now: float | None = None) -> bool:
        stamp = time.monotonic() if now is None else now
        with self._lock:
            kept = self._prune(address, stamp, settings.dispatch_unlock_window_seconds)
            return len(kept) >= settings.dispatch_unlock_max_failures

    def record_failure(self, address: str, settings: Settings, *, now: float | None = None) -> None:
        stamp = time.monotonic() if now is None else now
        with self._lock:
            kept = self._prune(address, stamp, settings.dispatch_unlock_window_seconds)
            kept.append(stamp)
            self._failures[address] = kept

    def clear(self, address: str) -> None:
        with self._lock:
            self._failures.pop(address, None)

    def verify_presented(
        self,
        address: str,
        settings: Settings,
        presented: str,
        expected: str,
        *,
        compare: Callable[[str, str], bool] | None = None,
        now: float | None = None,
    ) -> str:
        """Admit, compare, and record under one lock. Never compares when locked.

        Returns ``ok``, ``mismatch``, or ``locked``.
        """
        matcher = passcodes_match if compare is None else compare
        stamp = time.monotonic() if now is None else now
        with self._lock:
            kept = self._prune(address, stamp, settings.dispatch_unlock_window_seconds)
            if len(kept) >= settings.dispatch_unlock_max_failures:
                return "locked"
            if matcher(presented, expected):
                self._failures.pop(address, None)
                return "ok"
            kept.append(stamp)
            self._failures[address] = kept
            return "mismatch"


def attach_dispatch_auth(app: object, *, replace: bool = False) -> UnlockLimiter:
    """Hang a fresh lockout map on ``app.state`` so tests can isolate it."""
    existing = getattr(getattr(app, "state", None), "dispatch_unlock_limiter", None)
    if existing is not None and not replace:
        return existing
    limiter = UnlockLimiter()
    app.state.dispatch_unlock_limiter = limiter  # type: ignore[attr-defined]
    return limiter


def get_unlock_limiter(request: Request) -> UnlockLimiter:
    limiter = getattr(request.app.state, "dispatch_unlock_limiter", None)
    if limiter is None:
        limiter = attach_dispatch_auth(request.app)
    return limiter


def client_address(request: Request) -> str:
    """Direct peer address. Trusted-proxy forwarding is issue 13's work."""
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def passcodes_match(presented: str, expected: str) -> bool:
    """Timing-safe compare of equal-length digests, never raw-string ``==``."""
    return hmac.compare_digest(_digest(presented), _digest(expected))


def mint_actor() -> str:
    return "d_" + secrets.token_hex(8)


def sign_session(secret: str, actor: str) -> str:
    mac = hmac.new(_digest(secret), actor.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{actor}.{mac}"


def actor_from_session(secret: str, value: str) -> str | None:
    actor, separator, mac = value.partition(".")
    if separator != "." or not _ACTOR_RE.fullmatch(actor):
        return None
    expected = hmac.new(_digest(secret), actor.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(_digest(mac), _digest(expected)):
        return None
    return actor


def cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https"


def set_unlock_cookies(
    response: Response, request: Request, *, secret: str, actor: str, csrf: str
) -> None:
    secure = cookie_secure(request)
    response.set_cookie(
        COOKIE_SESSION,
        sign_session(secret, actor),
        httponly=True,
        path="/",
        samesite="lax",
        secure=secure,
    )
    response.set_cookie(
        COOKIE_CSRF,
        csrf,
        httponly=False,
        path="/",
        samesite="lax",
        secure=secure,
    )


def require_dispatch_passcode() -> str:
    secret = get_settings().dispatch_passcode
    if not secret:
        raise HTTPException(status_code=503, detail="DISPATCH_PASSCODE is not set")
    return secret


def actor_from_cookie(request: Request, secret: str) -> str | None:
    cookie = request.cookies.get(COOKIE_SESSION)
    if not cookie:
        return None
    return actor_from_session(secret, cookie)


def csrf_ok(request: Request) -> bool:
    header = request.headers.get(HEADER_CSRF, "")
    cookie = request.cookies.get(COOKIE_CSRF, "")
    if not header or not cookie:
        return False
    return hmac.compare_digest(_digest(header), _digest(cookie))


def require_desk_read(
    request: Request,
    secret: Annotated[str, Depends(require_dispatch_passcode)],
    limiter: Annotated[UnlockLimiter, Depends(get_unlock_limiter)],
    x_dispatch_passcode: Annotated[str | None, Header(alias=HEADER_PASSCODE)] = None,
) -> str:
    presented = (x_dispatch_passcode or "").strip()
    if presented:
        outcome = limiter.verify_presented(
            client_address(request), get_settings(), presented, secret
        )
        if outcome == "locked":
            raise HTTPException(
                status_code=429, detail="Too many unlock attempts. Try again later."
            )
        if outcome == "mismatch":
            raise HTTPException(
                status_code=401, detail="Unlock the desk to keep polling."
            )
        return "d_header"
    actor = actor_from_cookie(request, secret)
    if actor is None:
        raise HTTPException(
            status_code=401, detail="Unlock the desk to keep polling."
        )
    return actor


def require_desk_write(
    request: Request,
    actor: Annotated[str, Depends(require_desk_read)],
    x_dispatch_passcode: Annotated[str | None, Header(alias=HEADER_PASSCODE)] = None,
) -> str:
    """Cookie sessions need a CSRF token; a passcode header is sufficient."""
    if x_dispatch_passcode:
        return actor
    if not csrf_ok(request):
        raise HTTPException(
            status_code=403, detail="Desk write needs a CSRF token."
        )
    return actor
