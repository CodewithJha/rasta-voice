"""Shared RiderEvent contract: JSON schema, Pydantic, ingest, and TypeScript."""

from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from pathlib import Path

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.schema import Intent, RiderEvent, Urgency

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_frontend_types import (  # noqa: E402
    TYPES_PATH,
    differences,
    load_schema,
    parse_types,
)

LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, make_wav) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/tts/inference":
            return httpx.Response(200, content=make_wav(seconds=1.0, rate=16000))
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req-1",
                "transcript": LINE,
                "model": "prisma-v3.0",
                "detected_language_code": "hi-IN",
                "processing_time": 0.2,
            },
        )

    transport = httpx.MockTransport(handler)
    for cls in (PrismaSTT, TimbreTTS):
        monkeypatch.setattr(
            cls, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
        )
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    return seen


@pytest.fixture
def client(calls) -> TestClient:
    return TestClient(app)


def _schema() -> dict:
    return json.loads((ROOT / "shared" / "rider_event.schema.json").read_text())


def _normalize_types(node: dict) -> set[str]:
    if "anyOf" in node or "oneOf" in node:
        types: set[str] = set()
        for option in node.get("anyOf") or node.get("oneOf"):
            types |= _normalize_types(option)
        return types
    value = node.get("type")
    if value is None and "$ref" in node:
        return {"$ref"}
    if isinstance(value, list):
        return set(value)
    if isinstance(value, str):
        return {value}
    return set()


def _resolve(schema: dict, node: dict) -> dict:
    ref = node.get("$ref")
    if not ref:
        return node
    if not ref.startswith("#/"):
        raise AssertionError(f"unsupported $ref: {ref}")
    current: object = schema
    for part in ref[2:].split("/"):
        current = current[part]
    if not isinstance(current, dict):
        raise AssertionError(f"$ref {ref} did not point at an object")
    return current


def test_pydantic_schema_matches_shared_contract():
    shared = _schema()
    generated = RiderEvent.model_json_schema()

    assert set(generated["properties"]) == set(shared["properties"])
    assert set(generated.get("required", [])) == set(shared["required"])
    assert set(shared["required"]) == set(shared["properties"])
    assert generated.get("additionalProperties") is False

    for name, expected in shared["properties"].items():
        raw = generated["properties"][name]
        actual = _resolve(generated, raw)
        if "enum" in expected:
            actual_enum = actual.get("enum")
            if actual_enum is None and name == "intent":
                actual_enum = [item.value for item in Intent]
            if actual_enum is None and name == "urgency":
                actual_enum = [item.value for item in Urgency]
            assert actual_enum == expected["enum"], name
        expected_types = _normalize_types(expected)
        actual_types = _normalize_types(actual)
        if actual_types == {"$ref"} and "enum" in expected:
            actual_types = {"string"}
        # Pydantic uses `integer` for int and `number` for float, same as the
        # shared file. `null` must be present for optional fields.
        assert actual_types == expected_types, f"{name}: {actual_types} != {expected_types}"


def test_shared_schema_rejects_a_broken_event():
    schema = _schema()
    validator = jsonschema.Draft202012Validator(schema)
    good = RiderEvent(
        intent=Intent.delay,
        order_id="7",
        eta_minutes=20,
        urgency=Urgency.low,
        dispatch_action="Send the new ETA to the customer and leave the rider on this drop.",
        transcript="bhaiya 20 min late hoon, traffic mein, order 7",
        confidence=0.5,
    ).model_dump(mode="json")
    validator.validate(good)

    bad = dict(good)
    bad["intent"] = "not-an-intent"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)

    leftover = dict(good)
    leftover["extra"] = "nope"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(leftover)


def test_ingest_event_matches_shared_schema(client: TestClient, make_wav):
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=2.0), "audio/wav")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "event" in body
    jsonschema.Draft202012Validator(_schema()).validate(body["event"])
    # The envelope is not the event contract; it must still carry an event
    # that the frontend can assign to RiderEvent.
    assert set(_schema()["properties"]) <= set(body["event"])


def test_frontend_types_match_shared_schema():
    errors = differences(load_schema(), parse_types(TYPES_PATH.read_text(encoding="utf-8")))
    assert errors == [], "\n".join(errors)
