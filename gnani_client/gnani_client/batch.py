"""Prisma batch jobs.

Flow from the docs: create ``POST /stt/v3/batch/jobs``, then
``POST /stt/v3/batch/jobs/{id}/start``, poll
``GET /stt/v3/batch/jobs/{id}``, then
``GET /stt/v3/batch/jobs/{id}/files``. The files list carries a pre-signed
``transcript_url`` per file, not the text: :meth:`PrismaBatch.fetch_transcript`
downloads it (no API key, the URL expires after an hour).

``with_denoise`` cleans noisy audio before transcription. It exists on
batch only. Leave it off for clean clips.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any

import httpx

from gnani_client.env import base_url, require_api_key
from gnani_client.errors import GnaniError, error_message


def batch_config(
    *,
    model: str,
    language_code: str,
    with_denoise: bool = False,
    keyterms: list[str] | None = None,
    output_format: str | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    """Job ``config`` object.

    Prisma v3.0 takes ``keyterms`` (phrases allowed, max 200). Prisma v2.5
    rejects ``keyterms`` / ``format`` / ``topic`` with 400 INVALID_CONFIG, so
    single-word hints go in ``bias_list`` instead. ``bias_score`` is ignored
    on v3.0.
    """
    config: dict[str, Any] = {
        "model": model,
        "language_code": language_code,
        "mode": "transcribe",
        "with_denoise": with_denoise,
    }
    if model == "prisma-v3.0":
        if keyterms:
            config["keyterms"] = keyterms
        if output_format:
            config["format"] = output_format
        if topic:
            config["topic"] = topic
    elif keyterms:
        config["bias_list"] = keyterms
        config["bias_score"] = 1.0
    return config


class PrismaBatch:
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

    def create_job(
        self,
        clips: list[tuple[str, bytes]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        files: list[tuple[str, tuple[Any, ...]]] = [
            ("config", (None, json.dumps(config), "application/json")),
        ]
        for name, blob in clips:
            files.append(("files", (name, blob, "audio/wav")))
        return self._json("POST", "/stt/v3/batch/jobs", files=files)

    def start_job(self, job_id: str) -> dict[str, Any]:
        return self._json("POST", f"/stt/v3/batch/jobs/{job_id}/start")

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._json("GET", f"/stt/v3/batch/jobs/{job_id}")

    def list_files(self, job_id: str, status: str | None = "COMPLETED") -> dict[str, Any]:
        """Per-file rows under ``data``. Each completed row has ``transcript_url``."""
        params = {"status": status} if status else None
        return self._json("GET", f"/stt/v3/batch/jobs/{job_id}/files", params=params)

    def fetch_transcript(self, transcript_url: str) -> dict[str, Any]:
        """Download the transcript document (``full_transcript``, ``segments``)."""
        with self._http() as http:
            response = http.get(transcript_url)
        if response.status_code != 200:
            raise GnaniError(
                f"Transcript download {response.status_code}: the URL may have expired, "
                "call list_files again for a fresh one",
                status=response.status_code,
                body=response.text[:500],
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise GnaniError("Transcript document is not JSON", body=response.text[:500]) from exc

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with self._http() as http:
            response = http.request(
                method,
                f"{self.base}{path}",
                headers={"X-API-Key-ID": self.api_key},
                **kwargs,
            )
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise GnaniError(
                f"Batch {method} {path} returned non-JSON ({response.status_code})",
                status=response.status_code,
                body=response.text[:500],
            ) from exc
        if response.status_code not in {200, 201, 202}:
            message = error_message(response.text, f"Batch failed ({response.status_code})")
            raise GnaniError(
                f"Prisma batch {method} {path} {response.status_code}: {message}",
                status=response.status_code,
                body=response.text[:500],
            )
        return body

    def _http(self):
        if self._client is not None:
            return nullcontext(self._client)
        return httpx.Client(timeout=60.0)
