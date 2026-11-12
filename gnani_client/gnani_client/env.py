"""Env resolution shared by the STT, batch, and TTS clients."""

import os

DEFAULT_BASE_URL = "https://api.vachana.ai"


def api_key() -> str:
    return os.environ.get("GNANI_API_KEY", "").strip()


def base_url() -> str:
    return os.environ.get("GNANI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def mock_enabled(explicit: bool | None, key: str) -> bool:
    """Mock when asked, when GNANI_MOCK=1, or when no key is available.

    GNANI_MOCK=0 forces live calls. A missing key in that mode still fails
    at request time, which is what we want once credits arrive.
    """
    if explicit is not None:
        return explicit
    flag = os.environ.get("GNANI_MOCK", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    return not key


def ws_base(http_base: str) -> str:
    if http_base.startswith("https://"):
        return "wss://" + http_base.removeprefix("https://")
    if http_base.startswith("http://"):
        return "ws://" + http_base.removeprefix("http://")
    return http_base
