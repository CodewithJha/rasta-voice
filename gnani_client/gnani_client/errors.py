"""Errors raised by the Gnani clients."""

from __future__ import annotations

import json


class GnaniError(RuntimeError):
    """A Gnani call failed. ``status`` is the HTTP status when there was one."""

    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class MissingApiKeyError(GnaniError):
    """GNANI_API_KEY is empty. Raised before any request is built."""


def error_message(text: str, fallback: str) -> str:
    """Pull a readable message out of any documented Gnani error shape.

    STT: ``{"success": false, "error": {"type", "message"}}``.
    TTS / batch: ``{"success": false, "message": ...}``.
    Auth and rate limits: ``{"detail": {"error_code", "message"}}``.
    """
    try:
        body = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text[:300] or fallback
    if not isinstance(body, dict):
        return text[:300] or fallback
    err = body.get("error")
    if isinstance(err, dict) and isinstance(err.get("message"), str):
        kind = err.get("type")
        return f"{kind}: {err['message']}" if kind else err["message"]
    detail = body.get("detail")
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        code = detail.get("error_code")
        return f"{code}: {detail['message']}" if code else detail["message"]
    if isinstance(body.get("message"), str):
        return body["message"]
    return text[:300] or fallback
