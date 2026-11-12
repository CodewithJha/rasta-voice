#!/usr/bin/env python3
"""Fail if frontend/src/types.ts drifts from shared/rider_event.schema.json.

Compares RiderEvent field names and the Intent and Urgency enum values.
Used by the contract CI job. Also imported by backend/tests/test_contract.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "shared" / "rider_event.schema.json"
TYPES_PATH = ROOT / "frontend" / "src" / "types.ts"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _union_values(source: str, type_name: str) -> list[str]:
    pattern = rf"export type {re.escape(type_name)}\s*=\s*(.*?);"
    match = re.search(pattern, source, flags=re.S)
    if not match:
        raise SystemExit(f"{TYPES_PATH}: missing `export type {type_name}`")
    values = re.findall(r'"([^"]+)"', match.group(1))
    if not values:
        raise SystemExit(f"{TYPES_PATH}: `export type {type_name}` has no string values")
    return values


def _interface_fields(source: str, name: str) -> list[str]:
    pattern = rf"export interface {re.escape(name)}\s*\{{(.*?)\n\}}"
    match = re.search(pattern, source, flags=re.S)
    if not match:
        raise SystemExit(f"{TYPES_PATH}: missing `export interface {name}`")
    return re.findall(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\??\s*:", match.group(1))


def parse_types(source: str) -> dict[str, list[str]]:
    return {
        "intent": _union_values(source, "Intent"),
        "urgency": _union_values(source, "Urgency"),
        "fields": _interface_fields(source, "RiderEvent"),
    }


def differences(schema: dict, types: dict[str, list[str]]) -> list[str]:
    errors: list[str] = []
    properties = schema["properties"]
    schema_fields = list(properties)
    if types["fields"] != schema_fields:
        errors.append(
            "RiderEvent fields differ: "
            f"types.ts={types['fields']} schema={schema_fields}"
        )
    for name in ("intent", "urgency"):
        expected = properties[name]["enum"]
        if types[name] != expected:
            errors.append(
                f"{name} values differ: types.ts={types[name]} schema={expected}"
            )
    return errors


def main() -> int:
    schema = load_schema()
    source = TYPES_PATH.read_text(encoding="utf-8")
    errors = differences(schema, parse_types(source))
    if errors:
        print("frontend/src/types.ts is out of sync with shared/rider_event.schema.json:")
        for item in errors:
            print(f"- {item}")
        return 1
    print("frontend/src/types.ts matches shared/rider_event.schema.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
