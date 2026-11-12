"""Gemini generateContent caller (Google AI Studio free tier, via httpx)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from rasta.extractors.base import LlmError, MissingLlmKeyError
from rasta.extractors.breaker import ensure_closed
from rasta.extractors.http import request_with_retry, resolve_client
from rasta.extractors.parse import event_from_model_text
from rasta.extractors.prompt import SYSTEM_PROMPT, build_user_message
from rasta.schema import RiderEvent
from rasta.settings import Settings, get_settings

TEMPERATURE = 0
API_KEY_HEADER = "x-goog-api-key"


class GeminiExtractor:
    """Calls Gemini generateContent with temperature 0 and JSON mime type."""

    name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def extract(
        self,
        transcript: str,
        *,
        client: httpx.Client | None = None,
        sleeper=None,
    ) -> RiderEvent:
        """Return a validated event or raise ``LlmError``."""
        ensure_closed(self.name)
        cfg = self.settings
        key = cfg.gemini_api_key
        if not key:
            raise MissingLlmKeyError(cfg.key_env_name(self.name))
        http = resolve_client(client, cfg)
        url = gemini_url(cfg.gemini_base_url, cfg.gemini_model)
        payload = gemini_request_body(transcript)
        headers = {
            API_KEY_HEADER: key,
            "Content-Type": "application/json",
        }
        kwargs: dict[str, Any] = {"json": payload, "headers": headers}
        if sleeper is not None:
            response = request_with_retry(
                http, "POST", url, settings=cfg, sleeper=sleeper, **kwargs
            )
        else:
            response = request_with_retry(http, "POST", url, settings=cfg, **kwargs)
        text = _content_from_gemini(response)
        return event_from_model_text(text, transcript)


def gemini_url(base_url: str, model: str) -> str:
    """Return the generateContent URL. The key is sent as a header, not a query."""
    safe_model = quote(model, safe=".-_")
    return f"{base_url.rstrip('/')}/models/{safe_model}:generateContent"


def gemini_request_body(transcript: str) -> dict[str, Any]:
    """Return a generateContent body with a JSON-only response."""
    return {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": build_user_message(transcript)}]},
        ],
        "generationConfig": {
            "temperature": TEMPERATURE,
            "responseMimeType": "application/json",
        },
    }


def _content_from_gemini(response: httpx.Response) -> str:
    try:
        body = response.json()
        parts = body["candidates"][0]["content"]["parts"]
        texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
        content = "\n".join(piece for piece in texts if piece)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LlmError(
            "Gemini response was missing candidate text", reason="invalid_json"
        ) from exc
    if not content.strip():
        raise LlmError("Gemini response content was empty", reason="invalid_json")
    return content
