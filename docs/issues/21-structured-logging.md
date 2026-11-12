# 21 — Structured logging and request IDs

- **Labels:** `area:app`, `day:2`, `observability`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 2 (13–14 Nov 2026). Can land in parallel with 19 once you are not both editing `main.py` heavily. Feeds evidence for issues 17 and 18: a request id on the response and in the log is what the field report and the demo write-up quote.
- **Depends on:** skeleton merged. Does not wait on 07 or 13.

## Description

Every incoming request gets an id we control, and every Gnani call we make is logged as one JSON line we can grep later. Judges and the Day 3 write-ups need those ids. Operators need latency and status. Nobody needs a key or a wav in the log.

Middleware in the FastAPI app:

- Read `X-Request-ID` if the caller sent a safe token (for example a UUID or a short `[A-Za-z0-9._-]{1,128}` value). Otherwise mint a `uuid4`. Bind it on the request and set the `X-Request-ID` response header on every response, including 4xx/5xx and `/api/health`.
- Do not accept arbitrary header values that could break log parsing or inject newlines.

Around each Gnani call (in `backend/rasta/pipeline.py` and, once they exist, simulate / reply / stream / batch wrappers — not by rewriting `gnani_client/`), emit one JSON log record:

```json
{
  "request_id": "<ours>",
  "gnani_request_id": "<from the Gnani response, or null>",
  "endpoint": "/stt/v3",
  "latency_ms": 210,
  "status": 200,
  "audio_seconds": 6.08
}
```

`endpoint` is the Gnani path or a short name (`stt_rest`, `tts_inference`, `stt_stream`, `stt_batch`) consistent across calls. `status` is the HTTP status we got, or a short error token such as `timeout` after you have mapped it. `audio_seconds` is omitted or null when the call has no audio duration (for example a failed connect).

Never log `GNANI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `DISPATCH_PASSCODE`, raw audio bytes, base64 wavs, or the full transcript by default. A character count is fine. If you add a debug flag later, it stays off unless explicitly set, and it still must not print keys.

Use the stdlib `logging` module with a JSON formatter on the `rasta` logger. No paid observability vendor, no required third-party log host. Printing JSON to stdout is enough for a free host.

Tests: a `TestClient` call to `/api/health` returns `X-Request-ID`. A call that sends a safe id gets the same id back. A test of ingest with a swapped Gnani transport (`httpx.MockTransport` inside the test, same pattern as `test_ingest.py`) captures a log line that includes our id, a gnani request id from the fake response, endpoint, latency_ms, and status, and does not include the api key or the wav bytes.

## Files to touch

- `backend/rasta/logging.py` or `backend/rasta/request_id.py` (new)
- `backend/rasta/main.py` (middleware hookup)
- `backend/rasta/pipeline.py` (log around Prisma and Timbre calls)
- later call sites only if they already exist when you open the PR
- `backend/tests/test_logging.py` (new)
- `.env.example` only if you add a log-level var

## Do not touch

`gnani_client/` (call it, don't rewrite it), `frontend/`, `benchmark/`, `schema.py`. Do not add a paid log or telemetry vendor.

## Input / output contract

Every HTTP response includes `X-Request-ID`. The JSON log line for a successful sample ingest contains two Gnani records (Timbre then Prisma) or one combined record plus a child list — pick one shape and test it. Prefer one line per Gnani call, both sharing our request id.

`GET /api/health` does not call Gnani and does not need a Gnani log line, but it does return the header.

## Acceptance criteria

- [ ] `X-Request-ID` is present on health, ingest success, and ingest error responses (400/413/502/503).
- [ ] A safe incoming `X-Request-ID` is echoed; an unsafe one is replaced.
- [ ] Each Gnani call in the hello path writes a JSON log line with `request_id`, `gnani_request_id` (null if the upstream had none), `endpoint`, `latency_ms`, `status`, and `audio_seconds` when known.
- [ ] Tests assert the log line does not contain `GNANI_API_KEY`, audio bytes, or the full transcript.
- [ ] `pytest` and `ruff check backend` pass. No network.

## How to test

```bash
pytest backend/tests/test_logging.py backend/tests/test_ingest.py -q
curl -sD - http://127.0.0.1:8000/api/health -o /dev/null
curl -sD - -X POST http://127.0.0.1:8000/api/ingest/sample -o /tmp/sample.json
```

Confirm the response header and the process stdout have the same request id, and that the Prisma `request_id` in the JSON body matches `gnani_request_id` in the log. Paste those two ids in the PR, never the API key.

<!-- rasta-voice-production-2026-11-12 -->

### Production: redaction and volume

- [ ] After issue 28, logs must not print unredacted 8+ digit runs or full transcripts even if a debug flag is later added in non-prod. Prod refuses that flag.
- [ ] Bound log line size. Do not log request bodies, wav base64, cookies, or CSRF tokens.
- [ ] Retry attempts from issue 29 share the same `request_id` and add an `attempt` field (already asked in 29). This issue's formatter must not drop unknown extra keys.
- [ ] A test asserts a log record of a redacted transcript, if 28 has landed, does not contain `9876543210`.
