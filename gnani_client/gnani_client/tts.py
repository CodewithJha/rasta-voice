"""Timbre text-to-speech.

Live REST: POST {base}/api/v1/tts/inference
Header: X-API-Key-ID. Body is JSON. A 200 response is raw audio, not JSON.

Audio tags (``<whispers>``, ``<pauses>``, …) are honoured on
``timbre-v3.0`` only. On v2.5 they are stripped. Tag names are
case-sensitive and match the catalog, including the space in
``<clears throat>``.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any

import httpx

from gnani_client.env import api_key, base_url, mock_enabled
from gnani_client.errors import GnaniError
from gnani_client.wav import tone_wav

# Catalog from https://docs.gnani.ai/api/TTS/tts-audio-tags (timbre-v3.0).
AUDIO_TAGS = (
    "laugh",
    "giggle",
    "sigh",
    "exhales",
    "sniffles",
    "yawns",
    "coughs",
    "clears throat",
    "whispers",
    "shouting",
    "excited",
    "slow",
    "pauses",
)


class TimbreTTS:
    def __init__(
        self,
        key: str | None = None,
        *,
        mock: bool | None = None,
        base: str | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key() if key is None else key.strip()
        self.mock = mock_enabled(mock, self.api_key)
        self.base = (base or base_url()).rstrip("/")
        self._client = client

    def synthesize(
        self,
        text: str,
        *,
        voice: str = "Shivani",
        model: str = "timbre-v3.0",
        language: str = "hi-en",
        speed: float = 1.0,
        sample_rate: int = 16000,
        container: str = "wav",
    ) -> bytes:
        """Return a WAV (or other container) byte string.

        ``language="hi-en"`` is the Hinglish code from the TTS docs.
        Mock mode returns a short tone and does not speak the text.
        """
        if not text.strip():
            raise ValueError("TTS text is empty")
        if self.mock:
            return tone_wav()
        if not self.api_key:
            raise GnaniError("GNANI_API_KEY is empty and mock mode is off")
        payload: dict[str, Any] = {
            "text": text,
            "voice": voice,
            "model": model,
            "language": language,
            "speed": speed,
            "audio_config": {
                "sample_rate": sample_rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": container,
            },
        }
        with self._http() as http:
            response = http.post(
                f"{self.base}/api/v1/tts/inference",
                headers={
                    "X-API-Key-ID": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code != 200:
            message = _tts_error(response)
            raise GnaniError(message, status=response.status_code, body=response.text[:500])
        if not response.content:
            raise GnaniError("TTS returned an empty body", status=response.status_code)
        return response.content

    def _http(self):
        if self._client is not None:
            return nullcontext(self._client)
        return httpx.Client(timeout=60.0)


def _tts_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except json.JSONDecodeError:
        return response.text[:300] or f"TTS failed ({response.status_code})"
    if isinstance(body, dict):
        if isinstance(body.get("message"), str):
            return body["message"]
        detail = body.get("detail")
        if isinstance(detail, dict) and isinstance(detail.get("message"), str):
            return detail["message"]
    return response.text[:300]
