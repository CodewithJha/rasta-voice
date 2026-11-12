"""Prisma batch jobs.

Flow from the docs: create ``POST /stt/v3/batch/jobs``, then
``POST /stt/v3/batch/jobs/{id}/start``, poll
``GET /stt/v3/batch/jobs/{id}``, then
``GET /stt/v3/batch/jobs/{id}/files``. Transcript text is behind each
file's ``transcript_url`` on the live API. Mock mode returns
``full_transcript`` directly so the benchmark can run with no key.

``with_denoise`` cleans noisy audio before transcription. It exists on
batch only. Leave it off for clean clips.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any

import httpx

from gnani_client.env import api_key, base_url, mock_enabled
from gnani_client.errors import GnaniError
from gnani_client.stt import MOCK_TRANSCRIPT


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
        mock: bool | None = None,
        base: str | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key() if key is None else key.strip()
        self.mock = mock_enabled(mock, self.api_key)
        self.base = (base or base_url()).rstrip("/")
        self._client = client

    def create_job(
        self,
        clips: list[tuple[str, bytes]],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if self.mock:
            return {"job_id": "mock-job", "status": "CREATED", "mock": True}
        files: list[tuple[str, tuple[Any, ...]]] = [
            ("config", (None, json.dumps(config), "application/json")),
        ]
        for name, blob in clips:
            files.append(("files", (name, blob, "audio/wav")))
        return self._json("POST", "/stt/v3/batch/jobs", files=files)

    def start_job(self, job_id: str) -> dict[str, Any]:
        if self.mock:
            return {"job_id": job_id, "status": "STARTING", "mock": True}
        return self._json("POST", f"/stt/v3/batch/jobs/{job_id}/start")

    def get_job(self, job_id: str) -> dict[str, Any]:
        if self.mock:
            return {"job_id": job_id, "status": "COMPLETED", "mock": True}
        return self._json("GET", f"/stt/v3/batch/jobs/{job_id}")

    def list_files(self, job_id: str) -> dict[str, Any]:
        if self.mock:
            return {
                "job_id": job_id,
                "mock": True,
                "files": [
                    {
                        "name": "clip.wav",
                        "status": "COMPLETED",
                        "full_transcript": MOCK_TRANSCRIPT,
                    }
                ],
            }
        return self._json("GET", f"/stt/v3/batch/jobs/{job_id}/files")

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.api_key:
            raise GnaniError("GNANI_API_KEY is empty and mock mode is off")
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
            message = body.get("message") if isinstance(body, dict) else response.text
            raise GnaniError(str(message), status=response.status_code, body=response.text[:500])
        return body

    def _http(self):
        if self._client is not None:
            return nullcontext(self._client)
        return httpx.Client(timeout=60.0)
