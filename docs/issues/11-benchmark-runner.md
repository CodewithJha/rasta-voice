# 11 — Benchmark runner

- **Labels:** `area:benchmark`, `day:3`, `award`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026). Start as soon as issue 06 is in, including late on 13 Nov if the telephony manifest exists. The chart issue needs this file.
- **Depends on:** issue 06 (`phone_manifest.jsonl`). Uses `extract_event` as it stands; do not wait on the LLM, and do not change its signature.

## Description

Score Prisma on the phone-quality clips. This is the Noise Canceller entry. The runner must produce a real table in mock mode so CI and the README have a shape, and a live table when a key exists. Never present mock numbers as live numbers.

Systems, all through `PrismaBatch` and `batch_config` (not REST). REST has no `with_denoise`, and Prisma v2.5 rejects `keyterms`. `batch_config` already maps v2.5 hints to `bias_list` and v3.0 hints to `keyterms`. Use it.

| id | model | hints | with_denoise |
| --- | --- | --- | --- |
| `v25` | `prisma-v2.5` | none | false |
| `v25-bias` | `prisma-v2.5` | `order`, `gate`, `item`, `accident` (single words) | false |
| `v30` | `prisma-v3.0` | none | false |
| `v30-key` | `prisma-v3.0` | the same words, as keyterms | false |
| `v30-key-denoise` | `prisma-v3.0` | the same keyterms | true |

Language: `hi-IN,en-IN` on v3.0, `hi-IN` on v2.5 (v2.5 batch allows up to three codes; one is enough and avoids a surprise). Format `codemix` on v3.0 only.

Live flow per the docs: `create_job` → `start_job` → poll `get_job` until `COMPLETED` or a terminal failure → `list_files` → download each `transcript_url` and read `full_transcript`. Mock `list_files` already returns `full_transcript` and no URL. Handle both.

Cap the live default grid so a free credit pool survives: `--limit 8` utterances, all five noises, SNRs `10` and `0` only, all five systems. Print the call count before you start and refuse to run a live grid over 200 files unless `--i-mean-it` is passed. The full cartesian stays available for a local mock run.

Mock hypothesis: reference with the last whitespace-delimited word removed, for every system except `v30-key-denoise`, which uses the full reference. That makes WER non-zero and makes one system look better, so the chart has a shape. Stamp `"mock": true` on the output. A reader must not be able to miss it.

Scoring:

- WER and CER from `rasta_bench.score`, reference is the manifest `reference`.
- Intent: `extract_event(hypothesis, provider="mock")` and compare to the corpus intent (join on `id`). Accuracy is correct/total.
- Aggregate mean WER, mean CER, intent accuracy, per system, and also sliced by `noise` and by `snr_db`.

Write:

- `benchmark/results/scores.json`
- `benchmark/results/scores.md` — a Markdown table, system × mean WER × mean CER × intent accuracy, plus a second small table of WER by noise for `v30` vs `v30-key-denoise`.

If `GNANI_MOCK=0`, write `benchmark/results/scores.live.json` and `scores.live.md` instead, and do not overwrite the committed fixture unless `--commit-live` is passed. Add `scores.live.json` to `.gitignore` in this PR. The fixture `scores.json` is committed and its top-level `"mock": true` is what issue 12 plots if no live file exists.

Poll interval 10 seconds, as the docs suggest. Give up on a job after 15 minutes and record an error row rather than hanging the run.

## Files to touch

- `benchmark/rasta_bench/run.py` (new) — `python -m rasta_bench.run`
- `benchmark/tests/test_run.py` (new)
- `benchmark/results/scores.json` and `benchmark/results/scores.md` (generated fixture, committed)
- `.gitignore` (ignore `benchmark/results/scores.live.*`)

## Do not touch

`frontend/`, `backend/rasta/extract.py` (import it), `gnani_client/` unless `list_files` cannot see a `transcript_url` and you need one field copied through. The README benchmark section is issue 12.

## Input / output contract

Input: `benchmark/data/phone_manifest.jsonl` plus `benchmark/data/utterances.jsonl` for the gold intent.

`scores.json`:

```json
{
  "mock": true,
  "systems": [
    {"id": "v30-key-denoise", "wer": 0.0, "cer": 0.0, "intent_accuracy": 1.0, "n": 8}
  ],
  "by_noise": [
    {"system": "v30", "noise": "horn", "wer": 0.2, "n": 8}
  ]
}
```

Numbers in the fixture come from the mock hypothesis rule, not from your head. The test rebuilds a tiny manifest (two clips, two systems) in a temp dir and checks the math against `wer()`.

## Acceptance criteria

- [ ] A temp-dir test with mock on does not call `httpx` (patch the batch class to raise if constructed with `mock=False`, or assert `PrismaBatch.mock`).
- [ ] Fixture `scores.json` has `"mock": true`, five systems, and a markdown table with the same WER values.
- [ ] v2.5 systems do not send `keyterms` or `format` in the config. Assert on `batch_config` output inside the test, not only on the HTTP body.
- [ ] v3.0 denoise system sends `with_denoise: true`.
- [ ] Intent accuracy uses `extract_event` and the gold intent from the corpus id.
- [ ] Live mode is not required for CI. Document the exact command in the module docstring.
- [ ] `pytest benchmark/tests/test_run.py` passes offline.

## How to test

```bash
GNANI_MOCK=1 python -m rasta_bench.run --limit 4
pytest benchmark/tests/test_run.py -q
```

When a key exists:

```bash
GNANI_MOCK=0 python -m rasta_bench.run --limit 8
```

Read the printed file count before it starts uploading.
