# Rasta Voice

A noise-robust voice copilot for delivery riders. The rider speaks Hinglish on a phone-quality line ("bhaiya gate band hai, customer phone nahi utha raha"). Gnani Prisma transcribes it, a small extractor turns it into a dispatch event, and Gnani Timbre will speak a short confirmation back.

This repository is the skeleton: one working path from an audio upload to that event, on the real Gnani APIs. There is no mock or offline mode. Without `GNANI_API_KEY` the speech routes answer `503` with a clear message. The rest of the product is sequenced in [docs/PLAN.md](docs/PLAN.md). An honest production-readiness register, including the definition of done, is in [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md). How Himanshu and Priyanshu open branches and pull requests is in [CONTRIBUTING.md](CONTRIBUTING.md).

Built for Gnani AI's Great Indian AI Internship Challenge. Target award: **Noise Canceller**. Speech is synthetic. No real phone numbers, calls, or customer records.

Docs: [Current architecture](docs/ARCHITECTURE.md), [security and open gaps](docs/SECURITY.md), [contributing](docs/CONTRIBUTING.md). See the Operations and project policies section below for the runbook, ADRs,
license, changelog, conduct policy and governance.

## Team

The team is exactly these two people. No one else is a contributor.

- Member A, benchmark and audio: [Himanshu](https://github.com/himanshu748) (`@himanshu748`)
- Member B, app, realtime, and UI: [Priyanshu Jha](https://github.com/CodewithJha) (`@CodewithJha`)

## Layout

Himanshu and Priyanshu can work in parallel if they stay inside their trees.

| Path | Who | What |
| --- | --- | --- |
| `gnani_client/` | shared, treat as frozen | Prisma STT, batch jobs, Timbre TTS |
| `backend/rasta/` | Member B: Priyanshu Jha (@CodewithJha) | FastAPI hello path and, later, the live desk |
| `frontend/` | Member B: Priyanshu Jha (@CodewithJha) | Rider chit and dispatch slate |
| `benchmark/` | Member A: Himanshu (@himanshu748) | WER/CER now; noise, telephony, and the scored run later |
| `shared/rider_event.schema.json` | frozen | Event contract. Matching types live in `backend/rasta/schema.py` and `frontend/src/types.ts` |
| `docs/issues/` | both | One file per remaining slice of work |

## Architecture

Solid arrows are in this skeleton. Dashed arrows are the issue plan.

```mermaid
flowchart LR
  rider["Rider chit<br/>frontend"] -->|POST /api/ingest| api["FastAPI<br/>backend/rasta"]
  api --> stt["Prisma STT<br/>POST /stt/v3"]
  stt --> extract["Extractor<br/>free LLM, rules fallback"]
  extract --> event["RiderEvent JSON"]
  event --> slate["Dispatch slate"]
  event -.-> tts["Timbre TTS<br/>POST /api/v1/tts/inference"]
  tts -.-> rider
  mic["Live mic"] -.->|WebSocket /stt/v3/stream| stt
  bench["benchmark/"] -.->|noisy 8 kHz clips| batch["Batch STT<br/>with_denoise"]
  batch -.-> scores["WER, CER, intent accuracy"]
```

Gnani base URL: `https://api.vachana.ai`. Auth header on every call: `X-API-Key-ID`.

| Client | Live call | Notes |
| --- | --- | --- |
| `PrismaSTT.transcribe` | `POST /stt/v3` | `model=prisma-v3.0` is opt-in. Omit `model` for Prisma v2.5. REST clips are 30 seconds. |
| `stream_headers` | `wss://api.vachana.ai/stt/v3/stream` | Headers only. The socket loop is issue 07. `preset="telephony"` sets 8 kHz and the noisy-line VAD knobs. |
| `PrismaBatch` | `POST /stt/v3/batch/jobs`, then `/start` | `with_denoise` exists here, not on REST. Creating a job does not start it. `list_files` returns pre-signed `transcript_url`s; `fetch_transcript` downloads one. |
| `TimbreTTS.synthesize` | `POST /api/v1/tts/inference` | Default voice `Shivani`, model `timbre-v3.0`, language `hi-en` (Hinglish). Tags such as `<whispers>` are v3.0 only. |

Every client needs `GNANI_API_KEY` and raises `MissingApiKeyError` when it is empty. API failures raise `GnaniError` with the HTTP status and Gnani's error code (`401 INVALID_API_KEY`, `402` out of credit, `429 RATE_LIMITED`, …). The backend maps a missing key to `503` and an upstream failure to `502` with `upstream_status`.

The hello path asks Prisma v3.0 for `language_code=hi-IN,en-IN` and `format=transliterate`, and sends a short rider topic plus keyterms (`order`, `gate`, `customer`, `item`, `accident`, `traffic`). Transliterate returns the whole line in Latin script, so the extractor and the dispatcher read one script. Numbers come back as words ("order eighteen", "das minute"), and the extractor parses both words and digits.

Verified live on 12 Nov 2026: Timbre v3.0 (`Shivani`, `hi-en`, 16 kHz) spoke

> Bhaiya, gate band hai aur customer phone nahi utha raha. Order eighteen pe main das minute se khada hoon.

(6.1 s of audio), and Prisma v3.0 returned that line word for word. The event is `customer_unreachable`, order `18`, ETA `10` min, urgency `high`. The closed gate is in the words, and the contact failure wins. The same clip downsampled to 8 kHz with white noise at 5 dB SNR still came back with the same intent, order and ETA.

## Setup

Python 3.11+ and Node 22. From a clean checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Put your key in `.env` as `GNANI_API_KEY=…` (the API loads `.env` on start; real environment variables win). `.env` is gitignored, never commit it. `LLM_PROVIDER=rules` uses the keyword extractor, which needs no LLM key and is the fallback when a free-tier Groq or Gemini call fails. `groq` and `gemini` need `GROQ_API_KEY` or `GEMINI_API_KEY`. Defaults, timeout, and retry caps are listed in `.env.example` and documented in [docs/EXTRACTOR.md](docs/EXTRACTOR.md).

API:

```bash
uvicorn rasta.main:app --reload --port 8000
curl -s http://127.0.0.1:8000/api/health          # gnani_key_set must be true
curl -s -X POST http://127.0.0.1:8000/api/ingest/sample | python -m json.tool
curl -s http://127.0.0.1:8000/api/events | python -m json.tool
# later polls: /api/events?since=<last created_at>
```

Web (proxies `/api` to port 8000):

```bash
cd frontend
npm install
npm run dev
```

Open the printed localhost URL. **Speak a sample line** has Timbre say a synthetic rider line, sends that audio to Prisma, and fills the chit and the slate. It costs two API calls.

Upload a real clip with:

```bash
curl -s -X POST http://127.0.0.1:8000/api/ingest \
  -F audio_file=@clip.wav
```

Every upload is a live Prisma REST call (30 seconds max). The response includes `request_id`, `processing_time` and `audio_seconds`, plus an `id` and UTC `created_at`. `GET /api/events` lists stored ingest records (oldest first); `?since=` returns only newer ones. The list lives in process memory and clears on restart.

## Event

`shared/rider_event.schema.json` is the contract.

| Field | Meaning |
| --- | --- |
| `intent` | `customer_unreachable`, `address_issue`, `item_missing`, `delay`, `accident_sos`, or `other` |
| `order_id` | Short synthetic token. An 8-digit run is never promoted to an order id. |
| `eta_minutes` | Minutes the rider quoted, else null |
| `urgency` | `low`, `medium`, `high` |
| `dispatch_action` | One instruction for the desk |
| `transcript` | Text the extractor saw |
| `confidence` | Rules use `0.5` on a hit and `0.0` otherwise. An LLM may return its own number in `[0, 1]`. |

Change the JSON schema, `backend/rasta/schema.py`, and `frontend/src/types.ts` in the same commit. Envelope fields such as `extractor_source` (`llm` or `rules`) and `fallback_reason` stay next to `event`, never inside it.

Rules intent accuracy, measured 12 Nov 2026, is 8/36 = 0.222 on the blind holdout after the channel-bound contact fix (still below the 0.8 target, which remains open on issue 2; earlier official runs were 6/36). The development gold set is 30/30, the 24-line tuning holdout that was seen during rule expansion is 24/24, and Himanshu's benchmark corpus, which was not used for tuning, is 41/48. The write-up is in [docs/EXTRACTOR.md](docs/EXTRACTOR.md).

## Checks

```bash
ruff check gnani_client backend benchmark
pytest
cd frontend && npm run check
```

GitHub Actions runs the same three commands with no secrets. Tests swap the HTTP transport (`httpx.MockTransport`) inside the test files only; the app code has no fake path.

## What is deliberately not here

Noise mixing, the scored Prisma matrix, realtime streaming, the spoken reply, deployment, and the contest post. Those are issues, with owners and days, in [docs/PLAN.md](docs/PLAN.md).

<!-- benchmark:start -->

Synthetic rider speech was mixed with traffic, horn, wind, crowd and crosstalk,
then converted to simulated 8 kHz μ-law telephone audio. Five Prisma batch
systems compare v2.5 and v3.0, v2.5 bias hints, v3.0 keyterms and v3.0 denoise.
This is synthetic speech, not a real call corpus. Each system scores the same
80 unique clips; the complete default grid has 400 model evaluations.

| System | Raw WER | Raw CER | Normalized WER | Normalized CER | Intent accuracy | n |
| --- | --- | --- | --- | --- | --- | --- |
| v25 | 0.8429 | 0.8123 | 0.8012 | 0.8107 | 0.0000 | 80 |
| v25-bias | 0.8429 | 0.8123 | 0.8012 | 0.8107 | 0.0000 | 80 |
| v30 | 0.7461 | 0.5833 | 0.6546 | 0.5316 | 0.2250 | 80 |
| v30-key | 0.7439 | 0.5828 | 0.6546 | 0.5316 | 0.2250 | 80 |
| v30-key-denoise | 0.7292 | 0.5625 | 0.6334 | 0.5077 | 0.2000 | 80 |

![WER by system](benchmark/results/wer.svg)

Run: **13 Nov 2026, 15:04 IST** (`2026-11-13T09:34:05.153014+00:00`).
Grid: **8 utterances × 5 noises × 2 SNRs (0 and 10 dB) × 5 systems = 80 distinct
files and 400 completed evaluations**. The bars are per-system mean **raw WER**;
the table is copied from [scores.md](benchmark/results/scores.md).
[The live summary](benchmark/results/scores.json) records 20 batch job IDs and
links the per-evaluation audio/config hashes to [raw transcripts](benchmark/results/raw/).
Batch responses did not return request IDs; the recorded job IDs are not REST request IDs.

Normalization applies Unicode NFKC, case folding, punctuation/symbol removal,
whitespace folding, decimal-digit normalization, English 0-199 and Roman Hindi
0-30 number-word folding. It performs **no translation or script transliteration**. Between 58
and 60 of 80 hypotheses per system are cross-script relative to the references;
v3.0 used `format=codemix`. These descriptive WER results are **not a clean
model ranking**, and rules intent accuracy also reflects extractor script
coverage. Denoise is not uniformly better: raw WER falls for traffic, crowd and
crosstalk, but rises for horn and wind. The mean raw WER difference from v3.0 to
v3.0-key-denoise is 0.0169, while intent accuracy changes from 0.2250 to 0.2000.

Reproduce with `python -m rasta_bench.run --limit 8 --credit-budget <cap> --credits-per-minute <verified-rate>`
from the installed repository, with `GNANI_API_KEY` supplied privately. Preserve
cache/checkpoints to resume; do not automatically repeat a charged run. The cap
and rate are operator inputs, not a provider-reported balance. This run records
a cap of 40 and rate of 1.0, with a resume-time estimated new-credit upper bound
of 24.0533, excluding 40 previously cached evaluations. It does not establish an
actual charge or remaining balance. Audio is gitignored: restore the exact
matching WAVs or regenerate manifests with the pipeline before a new run;
Timbre output is not bit-stable. This default-grid regeneration used u01–u08,
so u08's crosstalk partner wraps to u01 rather than u09. To redraw only the
figure, run `python -m rasta_bench.chart`; that command makes no API calls.

<!-- benchmark:end -->

Opt-in live API smoke: `python scripts/smoke.py --base-url http://127.0.0.1:8000` (needs `DISPATCH_PASSCODE` locally when the remote speech key is set; no-key health skips with zero speech calls; configured targets must have issues 20/21/22/26 deployed; add `--require-security-headers` for the public origin after 27).

## Operations and project policies

- [Operator runbook](docs/RUNBOOK.md)
- [Deployment instructions and public-origin status](docs/DEPLOY.md)
- [Latency budgets and measured local baseline](docs/SLO.md)
- [Governance and branch protection](docs/GOVERNANCE.md)
- [Decision 1: real speech APIs](docs/adr/0001-real-speech-apis.md)
- [Decision 2: frozen event envelope](docs/adr/0002-frozen-event-envelope.md)
- [Decision 3: SQLite single-worker topology](docs/adr/0003-sqlite-single-worker.md)
- [Decision 4: shared desk passcode](docs/adr/0004-shared-desk-passcode.md)
- [MIT license](LICENSE), [changelog](CHANGELOG.md), [code of conduct](CODE_OF_CONDUCT.md)

Supply-chain checks and dependency-lock updates: [docs/SUPPLY_CHAIN.md](docs/SUPPLY_CHAIN.md).

Type, coverage, unit and browser checks: [docs/QUALITY.md](docs/QUALITY.md).
