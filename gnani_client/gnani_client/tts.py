"""Timbre text-to-speech.

Live REST: POST {base}/api/v1/tts/inference
Header: X-API-Key-ID. Body is JSON. A 200 response is raw audio, not JSON.

Audio tags (``<whispers>``, ``<pauses>``, …) are honoured on
``timbre-v3.0`` only. On v2.5 they are stripped. Tag names are
case-sensitive and match the catalog, including the space in
``<clears throat>``.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import httpx

from gnani_client.env import base_url, require_api_key
from gnani_client.errors import GnaniError, error_message

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
        base: str | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = require_api_key(key)
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
        Timbre streams WAV with placeholder sizes in the header; use
        :func:`gnani_client.wav.wav_duration_seconds` to measure it.
        """
        if not text.strip():
            raise ValueError("TTS text is empty")
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
            message = error_message(response.text, f"TTS failed ({response.status_code})")
            raise GnaniError(
                f"Timbre TTS {response.status_code}: {message}",
                status=response.status_code,
                body=response.text[:500],
            )
        if not response.content:
            raise GnaniError("TTS returned an empty body", status=response.status_code)
        return response.content

    def _http(self):
        if self._client is not None:
            return nullcontext(self._client)
        return httpx.Client(timeout=60.0)

