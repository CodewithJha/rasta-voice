"""Groq OpenAI-compatible chat completions caller."""

from __future__ import annotations

from typing import Any

import httpx

from rasta.extractors.base import MissingLlmKeyError
from rasta.extractors.breaker import ensure_closed
from rasta.extractors.http import request_with_retry, resolve_client
from rasta.extractors.parse import event_from_model_text
from rasta.extractors.prompt import SYSTEM_PROMPT, build_user_message
from rasta.schema import RiderEvent
from rasta.settings import Settings, get_settings

TEMPERATURE = 0
CHAT_COMPLETIONS_PATH = "/chat/completions"


class GroqExtractor:
    """Calls Groq with temperature 0 and a JSON response format."""

    name = "groq"

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
        key = cfg.groq_api_key
        if not key:
            raise MissingLlmKeyError(cfg.key_env_name(self.name))
        http = resolve_client(client, cfg)
        url = f"{cfg.groq_base_url}{CHAT_COMPLETIONS_PATH}"
        payload = groq_request_body(transcript, cfg.groq_model)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        kwargs: dict[str, Any] = {
            "json": payload,
            "headers": headers,
        }
        if sleeper is not None:
            response = request_with_retry(
                http, "POST", url, settings=cfg, sleeper=sleeper, **kwargs
            )
        else:
            response = request_with_retry(http, "POST", url, settings=cfg, **kwargs)
        text = _content_from_groq(response)
        return event_from_model_text(text, transcript)


def groq_request_body(transcript: str, model: str) -> dict[str, Any]:
    """Return the JSON body the issue specifies, plus a JSON response format."""
    return {
        "model": model,
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(transcript)},
        ],
    }


def _content_from_groq(response: httpx.Response) -> str:
    from rasta.extractors.base import LlmError

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LlmError("Groq response was missing message content", reason="invalid_json") from exc
    if not isinstance(content, str) or not content.strip():
        raise LlmError("Groq response content was empty", reason="invalid_json")
    return content
