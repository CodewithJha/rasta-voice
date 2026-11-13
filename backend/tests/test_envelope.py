"""Test-only envelope model; production RiderEvent remains frozen and strict."""

from contextlib import nullcontext
from datetime import datetime
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.schema import RiderEvent


class SpeechMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: str = Field(min_length=1)


class IngestEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: UUID
    created_at: datetime
    stt: SpeechMetadata
    event: RiderEvent
    extractor_source: str | None = None


@pytest.fixture
def stamped(monkeypatch, make_wav):
    """Exercise the actual route with transport replacement confined to this test."""
    def handler(request):
        if request.url.path.endswith("/tts/inference"):
            return httpx.Response(200, content=make_wav(seconds=1.0, rate=16000))
        return httpx.Response(200, json={
            "success": True, "request_id": "synthetic-contract-request",
            "transcript": "customer phone nahi utha raha order eighteen",
            "model": "prisma-v3.0", "detected_language_code": "hi-IN",
        })

    for cls in (PrismaSTT, TimbreTTS):
        monkeypatch.setattr(cls, "_http", lambda self: nullcontext(
            httpx.Client(transport=httpx.MockTransport(handler))))
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    with TestClient(app) as client:
        response = client.post("/api/ingest", files={
            "audio_file": ("synthetic.wav", make_wav(seconds=1.0), "audio/wav"),
        })
        assert response.status_code == 200, response.text
        yield client, response.json()


def test_actual_ingest_envelope_is_valid(stamped):
    _, body = stamped
    parsed = IngestEnvelope.model_validate(body)
    assert parsed.created_at.tzinfo is not None
    assert parsed.stt.request_id == "synthetic-contract-request"


def test_outer_envelope_allows_lifecycle_and_future_metadata(stamped):
    _, body = stamped
    body.update(state="new", version=1, future_metadata={"origin": "synthetic"})
    parsed = IngestEnvelope.model_validate(body)
    assert parsed.model_extra["future_metadata"] == {"origin": "synthetic"}
    assert parsed.model_extra["state"] == "new"
    assert parsed.model_extra["version"] == 1


@pytest.mark.parametrize("mutation", ["missing-intent", "forbidden-event-key"])
def test_envelope_still_rejects_a_broken_frozen_event(stamped, mutation):
    _, body = stamped
    if mutation == "missing-intent":
        del body["event"]["intent"]
    else:
        body["event"]["state"] = "new"
    with pytest.raises(ValidationError):
        IngestEnvelope.model_validate(body)


def test_sample_unwraps_to_the_same_ingest_contract(stamped):
    client, _ = stamped
    response = client.post("/api/ingest/sample?condition=noisy")
    assert response.status_code == 200, response.text
    outer = response.json()
    assert outer["condition"] == "noisy"
    assert outer["audio_base64"]
    assert IngestEnvelope.model_validate(outer["ingest"]).stt.request_id
