# 29 — Upstream resilience and graceful shutdown

- **Labels:** `area:app`, `day:2`, `api`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 2 (13–14 Nov 2026). Land early, once you are not mid-edit on `main.py` with 19 or 21. Other Day 3 issues assume a pooled client and a breaker. Closes ARCH-01, ARCH-02, REL-01, REL-02, REL-03, REL-05, PERF-01, PERF-03, CON-03, and part of ARCH-03.
- **Depends on:** skeleton. If 19 has landed, persist nothing extra except maybe breaker state in memory. A one-process breaker is enough.

## Description

Gnani and the free LLM will fail. The app has to fail small, not stall the whole process, and it must not retry its way through the credit budget.

Shared HTTP client:

- One process-wide `httpx.AsyncClient` (or a sync client used only from a worker thread) created in the lifespan and closed on shutdown. Pass it into `PrismaSTT`, `TimbreTTS`, `PrismaBatch`, and the issue 02 LLM helper. Do not rewrite the public signatures more than an optional `client=` (the constructors already take `client=`).
- Timeouts, from env with defaults: connect 5 s, read 15 s for REST STT, 20 s for TTS, 30 s for batch poll, and the issue 02 LLM timeout (4 s). Hard per-request deadline: 25 s for ingest, after which the rider gets 504 or 502 with `code=timeout` (issue 26 envelope if that has landed, otherwise a clear body that 26 can later wrap).

Event loop:

- Do not call blocking `http.post` on the event loop. Use the async client, or `asyncio.to_thread`. A test (or a documented assertion) fails if `ingest` is still invoked directly on the loop the way `main.py` lines 50–68 do today.

Retries:

- Retry only on 429, 502, 503, and transport/timeout errors, at most **twice** (three attempts total) for a single user action. Exponential backoff starting at 200 ms, plus full jitter. Do not retry 401, 402, or 4xx validation. Honour `Retry-After` when present, capped at 2 s.
- Every attempt counts against issue 13's global credit budget if a request actually left the process. If the budget would be exceeded by a retry, stop and return 429 `budget_exhausted`.
- Log each attempt with the issue 21 JSON fields (`request_id`, `attempt`, `status`, `latency_ms`). Never log the key.

Circuit breaker:

- Per upstream (`gnani_stt`, `gnani_tts`, `llm`): open after 5 failures in 60 s, stay open for 30 s, then half-open with one probe. While open, fail fast with 503 `circuit_open` and do not send a request (so we do not spend credits on a down API). Expose state on `/api/ready` once issue 22 exists.
- The rules extractor remains the LLM fallback (issue 02). A Gnani open breaker is not a licence to invent a transcript.

Concurrency: a process-wide semaphore, `RASTA_MAX_INFLIGHT` (default 4), around Gnani calls. Excess requests wait up to 3 s, then 429.

Shutdown: on lifespan exit, stop accepting new speech routes, wait up to 10 s for in-flight work, close the HTTP client, and close the SQLite connection (issue 19). Websocket routes (issue 07) drop with a close frame. A test uses a fake slow transport and a shutdown trigger, or documents a manual check if a clean unit test is too tight — prefer a unit test that the client is closed and the semaphore drains.

## Files to touch

- `backend/rasta/http.py` or `backend/rasta/resilience.py` (new: client, retry, breaker, semaphore)
- `backend/rasta/main.py` (lifespan start/stop, async routes)
- `backend/rasta/pipeline.py` (use the shared client)
- `gnani_client/` only if you must thread a default timeout through existing `client=` — prefer not to rewrite it; pass a configured client in.
- `backend/tests/test_resilience.py` (new)
- `.env.example` (timeouts, `RASTA_MAX_INFLIGHT=`, breaker knobs)

## Do not touch

Frontend, benchmark, frozen schema. Do not add a mock mode, a "skip Gnani" flag, or unbounded retries.

## Input / output contract

A swapped transport that fails once with 429 and then succeeds must produce one successful ingest and two observed attempts. A transport that fails 5 times opens the breaker; the next call returns 503 `circuit_open` with no sixth outbound HTTP call in that window.

## Acceptance criteria

- [ ] Shared client is created once and closed on shutdown.
- [ ] Ingest no longer blocks the event loop. `/api/health` remains snappy in a test where a dummy Gnani call is mid-flight (or the route is clearly `async` and uses `AsyncClient`).
- [ ] Retry policy matches the bounds above; a test proves 402 is not retried and that retries stop when the credit budget would be exceeded.
- [ ] Breaker tests for open, half-open, and success-to-close.
- [ ] Semaphore test for the 429-on-wait-timeout path.
- [ ] `pytest` and `ruff` pass. No network. No key in logs from the retry tests.

## How to test

```bash
pytest backend/tests/test_resilience.py backend/tests/test_ingest.py -q
```
