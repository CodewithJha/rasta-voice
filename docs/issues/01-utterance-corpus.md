# 01 — Synthetic Hinglish rider corpus

- **Labels:** `area:benchmark`, `day:1`, `synthetic-data`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 1 (12–13 Nov 2026)
- **Depends on:** skeleton merged. Nothing else.

## Description

Write the reference text the rest of the benchmark hangs on. These are lines a rider would shout on a bike in traffic, in Hinglish, mixed Latin and Devanagari where it sounds natural. They are invented. They are not transcripts of a real call.

Cover every intent in `shared/rider_event.schema.json`, including `other` (a line that is just the rider saying they are fine, or asking for water). Include these two, verbatim, as their own rows:

- `bhaiya gate band hai, customer phone nahi utha raha, order 18` → `customer_unreachable`, order `18`
- `order 4 mein ek item missing` → `item_missing`, order `4`

Aim for at least 40 rows, at least 6 per intent. Vary order tokens (`4`, `18`, `102`, none). Put an ETA only on some `delay` lines (`20 min`, `15 minute`). A few lines should stack a distractor ("gate band" plus "nahi utha") so later scoring has to pick the same winner the rules pick today.

Do not include phone numbers, Aadhaar-shaped numbers, real society names, or 8+ digit tokens. First names, if any, stay generic and unused as identifiers.

## Files to touch

- `benchmark/data/utterances.jsonl` (new)
- `benchmark/rasta_bench/corpus.py` (new) — `load_utterances(path) -> list[dict]`
- `benchmark/tests/test_corpus.py` (new)

## Do not touch

`backend/`, `frontend/`, `gnani_client/`, `shared/rider_event.schema.json`.

## Input / output contract

Each line of `utterances.jsonl` is one JSON object:

```json
{
  "id": "u01",
  "intent": "customer_unreachable",
  "order_id": "18",
  "eta_minutes": null,
  "text": "bhaiya gate band hai, customer phone nahi utha raha, order 18"
}
```

- `id`: `u` plus two digits, unique.
- `intent`: one of the schema enum values.
- `order_id`: string or null. Not a phone number.
- `eta_minutes`: integer or null, and `>= 0`.
- `text`: the reference transcript. No Timbre tags in this file. Tags are added later, in issue 03, on a copy.

`load_utterances` raises `ValueError` with the line number when a row breaks that shape.

## Acceptance criteria

- [ ] At least 40 rows, at least 6 for each of the six intents.
- [ ] The two sample lines above are present with the intents named.
- [ ] No digit run of length 8 or more anywhere in the file.
- [ ] `load_utterances` rejects a bad row, covered by a test that writes a temp file.
- [ ] `pytest benchmark/tests/test_corpus.py` passes without a network connection and without `GNANI_API_KEY`.

## How to test

```bash
pytest benchmark/tests/test_corpus.py -q
python -c "from rasta_bench.corpus import load_utterances; rows=load_utterances('benchmark/data/utterances.jsonl'); print(len(rows), {r['intent'] for r in rows})"
```
