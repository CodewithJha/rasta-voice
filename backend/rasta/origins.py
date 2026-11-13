"""Origin checks for browser speech routes. Never allow *."""

from __future__ import annotations

from urllib.parse import urlparse

from starlette.types import Scope

from rasta.settings import Settings


def forwarded_proto(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"x-forwarded-proto":
            first = value.decode("latin-1").split(",", 1)[0].strip().lower()
            return first or None
    return None


def request_http_scheme(scope: Scope, settings: Settings) -> str:
    """Return http or https for this request, honouring a trusted proxy."""
    if settings.trust_proxy_headers:
        proto = forwarded_proto(scope)
        if proto in {"https", "wss"}:
            return "https"
        if proto in {"http", "ws"}:
            return "http"
    scheme = str(scope.get("scheme") or "http").lower()
    if scheme in {"https", "wss"}:
        return "https"
    return "http"


def request_host(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"host":
            return value.decode("latin-1")
    return ""


def origin_allowed(origin: str | None, settings: Settings, scope: Scope) -> bool:
    """Allow an exact CORS entry or a strict same-origin match."""
    if not origin:
        return False
    if origin in settings.cors_allow_origins:
        return True
    parsed = urlparse(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not parsed.netloc
    ):
        return False
    host = request_host(scope)
    if not host or parsed.netloc.lower() != host.lower():
        return False
    return parsed.scheme == request_http_scheme(scope, settings)
