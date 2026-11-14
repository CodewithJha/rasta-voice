# Operator runbook

Checked against main `618147a` on 13 November 2026. The non-root production
image, deployment instructions, SQLite store, desk passcode, readiness, request
logs and upstream resilience are merged. The public URL is still unpublished
in [DEPLOY.md](DEPLOY.md); deployment and rollback are not verified by this
document. Issues 25, 26, 27 and 28 remain follow-up work at this checkpoint.
See [architecture](ARCHITECTURE.md), [security](SECURITY.md) and
[decisions](adr/0001-real-speech-apis.md).

## Boot locally

Use Python 3.11+ and Node 22. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn rasta.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Enter GNANI_API_KEY in the ignored `.env` with a local editor before starting
speech calls. The app loads that file; existing environment variables win.
Never put a key in command history or a screenshot. Rules need no LLM key.
In a second terminal, from `frontend/`, run `npm ci` then `npm run dev`.
Open Vite's printed local URL; its proxy serves `/api` and WebSockets from 8000.

Cheap checks, requiring no speech call:

```bash
curl --fail http://127.0.0.1:8000/api/health
curl --fail http://127.0.0.1:8000/api/ready
```

Health returns `ok`, `gnani_key_set` and `llm_provider`; it does not test provider
credit balance. Without a key, speech endpoints return 503. `/api/ready` checks
SQLite and reports the remaining local demo budget; it stays 200 for a missing
key or exhausted budget, with explicit flags. Unauthenticated `/api/events`
returns 401; unlock the desk before reading its contents.
To verify speech deliberately, use a synthetic sample once
through the rider UI: Timbre generates it and Prisma transcribes it, spending
two logical operations. Under issue 29's retry policy, each operation can have
an initial attempt plus two retries, for up to six provider attempts per sample.
The smoke CLI sends one sample POST with no client retry and reports
`SAMPLE_LOGICAL_OPERATIONS * (1 + server_retry_cap)` after dispatch, including
on timeout. The conservative default retry cap is two, giving six attempts.
Only when the remote deployment's configuration has been verified, supply its
cap with `--server-max-retries 0|1|2` or `RASTA_UPSTREAM_MAX_RETRIES`; the flag
overrides the environment. These are operator inputs, not remote discovery:
a local setting does not prove the remote host's cap. Leave the default when
unsure. Invalid or unsupported caps fail before HTTP requests with a zero bound.
Preflight failures and keyless skips report zero. This is not an exact bill;
the server's credit budget remains authoritative. Its separate confirmation
costs another uncached Timbre operation, outside the smoke CLI's single sample.
Do not run that check during an exhausted-credit incident.

## Environment inventory

The inventory below covers [.env.example](../.env.example) and the additional
log-line bound read by [settings.py](../backend/rasta/settings.py). Empty optional
numeric values select defaults; invalid numeric ranges fail validation. Restart
the process after changes. Keep all provider keys in host secrets or ignored
local `.env`, never in browser build variables.

| Variable | Default / purpose |
| --- | --- |
| GNANI_API_KEY | Empty; required for real speech |
| GNANI_BASE_URL | https://api.vachana.ai |
| LLM_PROVIDER | rules; optionally groq or gemini |
| GROQ_API_KEY | Empty; server-side Groq key |
| GEMINI_API_KEY | Empty; server-side Gemini key |
| LLM_MODEL | Empty; active-provider model override |
| GROQ_MODEL | Empty; settings.py selects the Groq default |
| GEMINI_MODEL | Empty; settings.py selects the Gemini default |
| GROQ_BASE_URL | Empty; settings.py selects the Groq base URL |
| GEMINI_BASE_URL | Empty; settings.py selects the Gemini base URL |
| LLM_TIMEOUT_SECONDS | Empty selects 4 seconds |
| LLM_MAX_RETRIES | Empty selects 1 retry; allowed 0 or 1 |
| LLM_RETRY_BACKOFF_SECONDS | Empty selects 0.25 seconds |
| EVENT_STORE_CAPACITY | 200 SQLite records; positive, at most 10000 |
| RASTA_DB_PATH | data/rasta-events.sqlite; writable file, never :memory: in the app |
| RASTA_MAX_STREAMS | 2 concurrent streams per process |
| RASTA_STREAM_SESSION_SECONDS | 900 seconds |
| RASTA_STREAM_IDLE_SECONDS | 60 seconds |
| RASTA_STREAM_HEARTBEAT_SECONDS | 20 seconds |
| RASTA_STREAM_DRAIN_SECONDS | 8 seconds |
| RASTA_STREAM_QUIET_SECONDS | 1 second |
| RASTA_STREAM_FRAME_BYTES | 1024 bytes; positive even PCM frame size |
| RASTA_STREAM_QUEUE_MAX | 32 queued frames |
| RASTA_STREAM_SAMPLE_RATE | 16000; also allows 8000, 44100, 48000 |
| CORS_ALLOW_ORIGINS | http://localhost:5173,http://127.0.0.1:5173 |
| DISPATCH_PASSCODE | Empty locally; desk routes fail closed; required in production |
| DISPATCH_UNLOCK_MAX_FAILURES | 5 failed attempts |
| DISPATCH_UNLOCK_WINDOW_SECONDS | 600 seconds |
| RASTA_LOG_LINE_MAX_BYTES | 4096 bytes per JSON log line |
| RASTA_ENV | development; production enables required-secret checks |
| RASTA_ALLOWED_HOSTS | Empty locally; required in production; image uses localhost,127.0.0.1,*.hf.space |
| RASTA_STATIC_DIR | Empty locally; image uses /app/frontend/dist |
| RASTA_DEMO_SPEECH_BUDGET | 40 production / 10000 development; 0 pauses speech |
| RASTA_DEMO_SPEECH_WINDOW_SECONDS | 86400 seconds |
| RASTA_PER_IP_REQUESTS_PER_MINUTE | 10 production / 10000 development |
| RASTA_TRUST_PROXY_HEADERS | false in source; true in platform image; trust only a controlled proxy |
| RASTA_MAX_SPEECH_SECONDS | 30 seconds |
| RASTA_MAX_CONCURRENT_SPEECH | 2 production / 32 development |
| RASTA_CONNECT_TIMEOUT_SECONDS | 5 seconds |
| RASTA_STT_READ_TIMEOUT_SECONDS | 15 seconds |
| RASTA_TTS_READ_TIMEOUT_SECONDS | 20 seconds |
| RASTA_BATCH_READ_TIMEOUT_SECONDS | 30 seconds |
| RASTA_INGEST_DEADLINE_SECONDS | 25 seconds |
| RASTA_MAX_INFLIGHT | 4 upstream speech attempts |
| RASTA_INFLIGHT_WAIT_SECONDS | 3 seconds |
| RASTA_UPSTREAM_MAX_RETRIES | 2 retries, allowed 0 to 2; each retry reserves budget |
| RASTA_UPSTREAM_RETRY_BACKOFF_SECONDS | 0.2 seconds, exponential with jitter |
| RASTA_RETRY_AFTER_CAP_SECONDS | 2 seconds |
| RASTA_BREAKER_FAILURE_THRESHOLD | 5 failures |
| RASTA_BREAKER_WINDOW_SECONDS | 60 seconds |
| RASTA_BREAKER_OPEN_SECONDS | 30 seconds before a half-open probe |
| RASTA_SHUTDOWN_DRAIN_SECONDS | 10 seconds, bounded graceful drain |

The exact origin list applies to HTTP CORS and WebSocket Origin checks. Empty
explicitly denies cross-origin requests; `*` is rejected. The image uses an
empty list for same-origin serving. Desk cookies have CSRF tokens for protected
writes and the signed pre-auth unlock handshake documented in SECURITY.md.
CSP and response security headers cover errors as well as successes. Configuration
ranges and provider defaults are authoritative in settings.py. Do not assume
that every future setting is implemented because it appears in an issue.

## Production boot and topology

Follow [DEPLOY.md](DEPLOY.md) for the free Hugging Face Docker Space and the
Render free-service backup. The root Dockerfile builds the frontend, installs
locked runtime dependencies and runs as non-root. Its entrypoint uses one
uvicorn worker and port 7860 (or the host's PORT). Production requires a desk
passcode and allowed hosts. Put keys and the passcode in host secrets, never
in a Docker build argument or frontend bundle. Set limits before opening traffic.

Check health, readiness, missing-credential rejection and the built frontend on
the actual HTTPS origin. Record its URL, exact deployed revision and limits.
Issue 24's configured live smoke also requires the consistent error envelope
(26), and the strict header check requires issue 27. A keyless skip is not a
successful public speech test. Do not report those checks as complete yet.

Run exactly one worker and one replica. SQLite is file-backed and survives a
process restart on the same disk. Stream slots, reply cache, rate limits,
credit reservations and breakers remain process-local; restart resets those
controls. Keep speech paused during an incident restart until the remaining
provider balance and an appropriate new cap have been verified. Multiple
workers or replicas require a reviewed shared-state design. Free-host rebuilds
can erase SQLite; no durable-host or off-site-backup guarantee is made.

## Credit exhaustion and pausing

A missing Gnani key returns 503. A zero or exhausted local speech budget also
returns 503; per-IP and concurrency rejection can return 429. Upstream Gnani
credit failure is surfaced as 502 with upstream status 402. The upstream
resilience layer may also report a structured timeout or circuit-open code.
Inspect the actual route response, not only the liveness status. Readiness
reports the local reservation budget, not Gnani's account balance, and stays
200 for a missing key or exhausted budget when SQLite remains usable.

1. Set `RASTA_DEMO_SPEECH_BUDGET=0` in the host configuration and restart, or
   pause the Space through its control panel. The environment is cached;
   changing a secret requires a restart. This stops new admissions, not work
   already in flight. Hiding a button does not block direct API callers.
2. Check the provider dashboard privately. Do not repeat paid samples or POSTs
   to diagnose balance. Retries reserve additional budget; request counts and
   actual provider charges are different measurements.
3. For a compromised Gnani key, revoke it at the provider, create a replacement,
   update the host secret and restart with speech still paused. Verify privately
   that the old key is revoked. Never print either value or commit it.
4. To rotate `DISPATCH_PASSCODE`, replace the host secret and restart. Existing
   signed cookies then fail verification. Confirm old credentials are rejected
   and the new passcode unlocks the desk. This does not add individual accounts.
5. Re-enable only after choosing a cap consistent with the verified remaining
   balance and planning one bounded synthetic check. If posts link a paused
   demo, say it is paused for credit checks. Link a recorded working demo only
   when that recording actually exists. Do not replace live speech with fake
   transcripts during an outage.

## Incident notes

Record UTC time, deployed revision, route, HTTP status and sanitized upstream
status. Capture `/api/ready`, response `X-Request-ID` and recent redacted JSON
logs with the same request ID. Readiness includes the store schema version,
event count, breaker states and local budget. The usage dashboard/endpoint is
issue 25 at this checkpoint; include it only after that implementation lands.
Never paste authorization headers, passcodes, signed URLs, raw audio or customer
transcripts into public issues. Desk events and database exports require
credentials but can contain transcripts: keep all incident examples synthetic
and inspect logs before sharing them. Privacy retention/deletion is still issue 28.

## Rollback

Keep the last verified deployed commit and configuration revision before every
release. Once a host exists, pause traffic, preserve any recoverable database,
select the previous verified image tag or deploy the exact previous main commit
through that host, and restore compatible configuration. No release tag/image
or deployed rollback target exists today; do not invent `v0.1.0`. Read any future
SQLite migration's downgrade guidance before reverting code; do not run an old
binary against an incompatible database. Restart one worker, run cheap checks,
then a budgeted synthetic smoke check before reopening traffic. Record outcome.
A local code rollback can use an isolated checkout of the verified commit;
never force-push main or erase another owner's branch.

## Backup and recovery

SQLite is stored at `RASTA_DB_PATH` (image default `/app/data/rasta-events.sqlite`).
The protected `GET /api/admin/export` downloads a consistent SQLite online-backup
snapshot. Unlock the desk first and download through its authenticated session;
keep cookies and passcodes out of command history, recordings and public logs.
Store the download privately, never in Git or public CI artifacts. The response
cleans up its temporary host copy after transfer; the export is not an off-site
backup service or a retention policy.

Before restoring, pause speech and stop the single writer. Check the snapshot
with SQLite `PRAGMA integrity_check`, then restore into an isolated instance
using the same code/schema revision and a separate file path. Verify expected
synthetic events before replacing the target file through the host's supported
private file transfer or shell. Do not overwrite a live database or copy only
the main file while WAL writes are active. Confirm the host actually supports
that transfer before promising recovery. If ephemeral disk is already gone and
no snapshot was saved, this procedure cannot recover it. Automated off-site
backups and public restore drills remain issue 35.

## Follow-up documents

[Production readiness](PRODUCTION_READINESS.md) tracks unfinished safeguards.
[Deployment](DEPLOY.md), [latency budgets and measured local baseline](SLO.md),
[load checks](../loadtest/README.md), [quality gates](QUALITY.md) and
[supply-chain checks](SUPPLY_CHAIN.md) describe merged tooling. SLO measurements
are revision-specific local evidence, not public-host or live-speech results.
API contract documentation is still issue 26. The governance record retains
the administrator-bypass limitation; this PR does not accept it for either owner.
