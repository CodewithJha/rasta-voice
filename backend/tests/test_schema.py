import json
from pathlib import Path

from rasta.schema import RiderEvent

ROOT = Path(__file__).resolve().parents[2]


def test_pydantic_fields_match_the_json_schema():
    document = json.loads((ROOT / "shared" / "rider_event.schema.json").read_text())
    assert set(RiderEvent.model_fields) == set(document["properties"])
    assert set(document["required"]) == set(document["properties"])
    intents = document["properties"]["intent"]["enum"]
    assert "customer_unreachable" in intents
    assert "accident_sos" in intents


def test_typescript_names_the_same_intents():
    source = (ROOT / "frontend" / "src" / "types.ts").read_text()
    document = json.loads((ROOT / "shared" / "rider_event.schema.json").read_text())
    for name in document["properties"]["intent"]["enum"]:
        assert f'"{name}"' in source
    for name in document["properties"]["urgency"]["enum"]:
        assert f'"{name}"' in source
    for field in document["properties"]:
        assert field in source
