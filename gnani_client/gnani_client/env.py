"""Env resolution shared by the STT, batch, and TTS clients."""

import os

from gnani_client.errors import MissingApiKeyError

DEFAULT_BASE_URL = "https://api.vachana.ai"


def api_key() -> str:
    return os.environ.get("GNANI_API_KEY", "").strip()


def require_api_key(explicit: str | None = None) -> str:
    """Return the key or raise. Every client calls the live API, always."""
    key = api_key() if explicit is None else explicit.strip()
    if not key:
        raise MissingApiKeyError(
            "GNANI_API_KEY is not set. Rasta Voice only talks to the real Gnani "
            "APIs: put your key in .env or the environment and restart."
        )
    return key


def base_url() -> str:
    return os.environ.get("GNANI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def ws_base(http_base: str) -> str:
    if http_base.startswith("https://"):
        return "wss://" + http_base.removeprefix("https://")
    if http_base.startswith("http://"):
        return "ws://" + http_base.removeprefix("http://")
    return http_base
