"""Load synthetic rider references without network access or speech credentials."""

import json
import re
from pathlib import Path

# Kept independent of the backend; tests check this against the shared contract.
INTENTS = frozenset({
    "customer_unreachable", "address_issue", "item_missing", "delay", "accident_sos", "other",
})
_FIELDS = {"id", "intent", "order_id", "eta_minutes", "text"}
_ID = re.compile(r"u[0-9]{2}")
_LONG_DIGITS = re.compile(r"\d{8,}")
_TAG = re.compile(r"<[^>]*>")


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    row = {}
    for key, value in pairs:
        if key in row:
            raise ValueError(f"duplicate field {key!r}")
        row[key] = value
    return row


def load_utterances(path: str | Path) -> list[dict]:
    """Return JSONL rows unchanged, or raise ValueError naming the invalid line.

    Each physical line must contain exactly the five corpus fields. References
    are untagged text; speech styles belong to a later synthesis manifest.
    Count and intent balance are dataset acceptance checks, not loader limits,
    so callers can also load a small corpus subset.
    """
    rows = []
    seen = set()
    with Path(path).open("rb") as source:
        for line_number, raw in enumerate(source, start=1):
            try:
                line = raw.decode("utf-8")
                if _LONG_DIGITS.search(line):
                    raise ValueError("digit runs of 8 or more are not allowed")
                row = json.loads(line, object_pairs_hook=_unique_fields)
                if not isinstance(row, dict) or row.keys() != _FIELDS:
                    raise ValueError(
                        "expected an object with id, intent, order_id, eta_minutes, text"
                    )
                identifier = row["id"]
                if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
                    raise ValueError("id must be 'u' followed by two ASCII digits")
                if identifier in seen:
                    raise ValueError(f"duplicate id {identifier!r}")
                if not isinstance(row["intent"], str) or row["intent"] not in INTENTS:
                    raise ValueError("intent must be a shared-schema enum value")
                order = row["order_id"]
                if order is not None and (not isinstance(order, str) or not order.strip()):
                    raise ValueError("order_id must be a nonempty string or null")
                eta = row["eta_minutes"]
                if eta is not None and (type(eta) is not int or eta < 0):
                    raise ValueError("eta_minutes must be a nonnegative integer or null")
                text = row["text"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("text must be a nonempty string")
                # Also check decoded strings, so JSON Unicode escapes cannot hide digits.
                if _LONG_DIGITS.search(json.dumps(row, ensure_ascii=False)):
                    raise ValueError("digit runs of 8 or more are not allowed")
                if _TAG.search(text):
                    raise ValueError("text must not contain Timbre or other markup tags")
            except ValueError as exc:
                raise ValueError(f"line {line_number}: {exc}") from exc
            seen.add(identifier)
            rows.append(row)
    return rows
