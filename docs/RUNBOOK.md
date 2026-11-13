# Operator runbook

This is the current development runbook, based on main `c9c3693` on
13 November 2026. Production deployment (13) has not landed: no production URL,
Dockerfile or DEPLOY.md is available. Proposed procedures below are conditional.
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
The smoke CLI sends one sample POST with no client retry and reports that
conservative six-attempt upper bound after dispatch, including on timeout.
Preflight failures and keyless skips report zero. This is not an exact bill;
the server's credit budget remains authoritative. Its separate confirmation
costs another uncached Timbre operation, outside the smoke CLI's single sample.
Do not run that check during an exhausted-credit incident.

## Environment inventory

These are all variables in [.env.example](../.env.example). Empty optional
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
| EVENT_STORE_CAPACITY | 200 in-memory records; positive, at most 10000 |
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

The same exact origin list already applies to HTTP CORS and WebSocket Origin
checks. Empty explicitly denies all Origins; `*` is rejected. Issue 27 owns CSP,
security headers, CSRF and further Origin hardening. Actual bounds
and provider defaults live in [settings.py](../backend/rasta/settings.py).
DISPATCH_PASSCODE, a database path and global budget variables are **not current
settings**. Setting an invented budget variable to zero will not stop spending.

## Production boot and topology

Until issue 13 supplies a reviewed deployment, keep the app local. A public
speech demo needs deployment, credit controls, desk auth, retention and readiness
work described in the readiness register. After that lands: follow its DEPLOY.md,
set provider secrets in the host's secret panel, build the frontend, use its
same-origin serving configuration, start exactly one worker without `--reload`,
and check liveness, readiness and one explicitly budgeted synthetic interaction.
Record the public URL, deployed commit and configured limits in deployment docs.
This file does not certify an untested production command or host.

Use one worker now because the store, stream slots and reply limits/cache are
process-local. Restart clears events and cache. Proposed SQLite also uses one
worker; multiple replicas need a separately reviewed shared-state design.

## Credit exhaustion and pausing

A missing Gnani key produces HTTP 503. Gnani failure is wrapped as HTTP 502
with `detail.upstream_status`, including upstream 402 for exhausted credit or
429 for provider throttling. Local reply concurrency/rate controls can also
return 429; inspect the sanitized status before deciding it is a credit outage.
A liveness 200 does not establish available credit. Readiness and shared usage
endpoints are pending issues 22 and 25, so their incident evidence is unavailable.

1. Stop new speech work. Locally stop the API process. On the eventual host,
   pause/stop the app using its control panel. Hiding a frontend button alone
   does not block direct API callers. No global budget-of-zero switch exists yet.
2. Inspect the provider dashboard privately and confirm balance/rate limits.
   Avoid repeatedly clicking samples or retrying a paid POST.
3. For a compromised key, revoke it at the provider, create a replacement there,
   update GNANI_API_KEY in host secrets (or ignored `.env`) and restart. Confirm
   the old key is revoked without printing either value. Secret changes never
   go in Git. Re-enabling requires explicit budget and a bounded speech check.
4. DISPATCH_PASSCODE rotation is conditional on issue 20: update that host secret,
   restart as its implementation requires, invalidate old sessions, and test
   old-credential rejection/new-credential acceptance. Today the setting has no
   effect; pausing the API is the available control.
5. If public posts link a paused demo, add a truthful status: "The live demo is
   paused while we check the speech-credit budget. The repository and recorded
   working-app demo remain available." Only say a recording is available if it
   actually is. Do not fabricate cached transcripts to keep the demo looking live.

## Incident notes

Record UTC time, deployed commit, route, HTTP status, sanitized upstream status,
and reproduction using synthetic input. Current liveness is `/api/health`;
`/api/ready`, X-Request-ID, structured JSON logs and shared usage evidence are
not implemented yet (22, 21 and 25). After they land, copy the readiness result,
request ID, recent redacted JSON log entries and usage totals into private
incident notes. Never include authorization headers, passcodes, signed URLs,
raw audio or customer transcripts in public issues. Check logs before sharing.
Current events are public and volatile, so use synthetic data only.

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

There is no SQLite file to download today: the in-memory store is not durable
and has no implemented export. Restart loses it. After issue 19 lands, identify
the configured database path in DEPLOY.md. Before stopping a still-running host,
use SQLite's online backup operation through the approved host shell, then
transfer the resulting snapshot through the host's authenticated download
facility to a private location. If using file copy instead, stop the single
writer first and account for any WAL files; do not copy just the live main file.
Run `PRAGMA integrity_check` on the snapshot and test restoration in an isolated
instance before calling it a backup. Do not place the database in Git or a public
artifact. The path, shell/download support and restore command must be verified
when persistence and hosting land. If disk is already gone, it cannot be
recovered by this procedure. Free-host disk is ephemeral; off-site backups and
restore drills are issue 35. Do not promise recovery until those exist.

## Follow-up documents

[Production readiness](PRODUCTION_READINESS.md) tracks unfinished safeguards.
DEPLOY.md (13), API.md (26) and SLO.md (31) do not exist at this revision; add
links after those files land. No measured SLO or load result is claimed here.
