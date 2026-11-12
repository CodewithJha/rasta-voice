# 03 — Clean clips from Timbre

- **Labels:** `area:benchmark`, `day:1`, `tts`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 1 (12–13 Nov 2026)
- **Depends on:** issue 01 (the jsonl must exist).

## Description

Turn each corpus line into a clean speech clip using the Timbre client that is already in the repo. This is the "before noise" stem. Later issues dirty it on purpose.

Use `TimbreTTS` from `gnani_client`. Do not edit `gnani_client/tts.py`.

Defaults, matching the client and the docs:

- model `timbre-v3.0`
- voice `Shivani`
- language `hi-en`
- container `wav`
- sample rate `16000`

`GNANI_MOCK=1` (the default with no key) must still write a WAV per row, marked `"mock": true` in the manifest. The bytes will be the client's tone. That is enough to build the mixer. When a key exists, run once with `GNANI_MOCK=0` and commit the manifest with `"mock": false` only if you are sure the wavs were real speech. Wav bytes stay gitignored under `benchmark/data/audio/`.

Reference text used later for WER is the corpus `text`, with no angle-bracket tags. You may pass Timbre a `spoken_text` that adds a single tag from `gnani_client.tts.AUDIO_TAGS` on at most 4 rows (a `<pauses>` on a delay, a `<whispers>` on an accident). Store both strings. Never put the tag in `reference`.

Skip the network entirely when mock is on. One live run is a loop of REST calls. Sleep briefly if you get HTTP 429. Do not parallelise into the rate limit.

## Files to touch

- `benchmark/rasta_bench/speak.py` (new) — `python -m rasta_bench.speak`
- `benchmark/tests/test_speak.py` (new)
- `benchmark/data/clean_manifest.jsonl` (generated; commit the mock manifest)

## Do not touch

`backend/`, `frontend/`, `gnani_client/`, the corpus file except to read it.

## Input / output contract

Input: `benchmark/data/utterances.jsonl`.

Output manifest, one JSON object per line:

```json
{
  "id": "u01",
  "reference": "bhaiya gate band hai, customer phone nahi utha raha, order 18",
  "spoken_text": "bhaiya gate band hai, customer phone nahi utha raha, order 18",
  "path": "benchmark/data/audio/clean/u01.wav",
  "voice": "Shivani",
  "model": "timbre-v3.0",
  "sample_rate": 16000,
  "sha256": "<hex of the wav bytes>",
  "mock": true
}
```

Each path is a mono 16-bit WAV. `sha256` matches the file. Re-running with the same mock tone overwrites the file and keeps the hash stable.

## Acceptance criteria

- [ ] `python -m rasta_bench.speak` with mock on writes one wav per corpus row and a manifest line each.
- [ ] Every wav starts with `RIFF`, sample rate 16000, mono, 16-bit. A test checks one file with the stdlib `wave` module.
- [ ] `reference` equals the corpus text. Tags, if any, appear only in `spoken_text`.
- [ ] Wav directory is gitignored (already in `.gitignore` as `benchmark/data/audio/`). The manifest is committed.
- [ ] No API key required for the test.

## How to test

```bash
GNANI_MOCK=1 python -m rasta_bench.speak
pytest benchmark/tests/test_speak.py -q
python -c "import wave; w=wave.open('benchmark/data/audio/clean/u01.wav'); print(w.getframerate(), w.getnchannels(), w.getsampwidth())"
```
