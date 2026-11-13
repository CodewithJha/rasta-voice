# Deploy

Public URL: _not published yet — paste the Space URL here after the
first successful deploy._

Hugging Face Spaces (Docker SDK) is the default host: one process, port
`7860`, no paid plan, no extra database. Render's free web service is the
documented backup if Spaces rejects the repo. Do not put secrets in the
Dockerfile or in a committed `.env`.

This note also covers process secrets the desk and speech paths need.

## Required environment

Set these in the process environment, Space secrets, or an ignored `.env`
file. Do not commit values, print them, or add them to health or ready
payloads.

- `GNANI_API_KEY` — Prisma and Timbre. If it is missing, the app still
  boots and `/api/health` reports `gnani_key_set: false`; speech routes
  return 503.
- `DISPATCH_PASSCODE` — shared desk passcode. Required to boot when
  `RASTA_ENV=production`. If it is missing in development, `GET
  /api/events`, `POST /api/dispatch/unlock`, and later desk write or ack
  routes return 503 with `DISPATCH_PASSCODE is not set`. The rider routes
  stay public.

Optional lockout knobs, with defaults of 5 failures in 600 seconds:

- `DISPATCH_UNLOCK_MAX_FAILURES`
- `DISPATCH_UNLOCK_WINDOW_SECONDS`

Also set, for a public Space:

- `RASTA_ENV=production` (the image already sets this)
- `RASTA_ALLOWED_HOSTS` — comma-separated hosts for
  `TrustedHostMiddleware`. The image default is
  `localhost,127.0.0.1,*.hf.space`. Starlette only treats `*.hf.space` as a
  subdomain suffix; a leading `.hf.space` is normalized to that form. Add a
  custom domain if you use one. A bare `*` is rejected.
- `CORS_ALLOW_ORIGINS` — empty in the image so the UI and API are
  same-origin. Do not set this to `*`.
- `RASTA_TRUST_PROXY_HEADERS=true` on Spaces or Render so per-IP limits
  see the platform's `X-Forwarded-For`. Leave it unset or `false`
  locally; untrusted clients can otherwise spoof the header.
- `RASTA_STATIC_DIR` — the image sets `/app/frontend/dist`.
- `RASTA_DEMO_SPEECH_BUDGET` — global Gnani-call cap per
  `RASTA_DEMO_SPEECH_WINDOW_SECONDS` (default 40 calls per 24 hours in
  production). `0` pauses public speech and returns 503, with no fake
  offline fallback.
- `RASTA_PER_IP_REQUESTS_PER_MINUTE` — default 10 in production.
- `RASTA_MAX_CONCURRENT_SPEECH` — production default 2; development default 32 so local and test suites can run concurrent uploads.
- `RASTA_MAX_SPEECH_SECONDS` — default 30 for ingest and simulate.
- `LLM_PROVIDER` and, if not `rules`, `GROQ_API_KEY` or `GEMINI_API_KEY`.
- `RASTA_DB_PATH` — SQLite file for the dispatch event store. The
  default is `data/rasta-events.sqlite` relative to the process
  working directory (in the image, `/app/data/rasta-events.sqlite`).
  The image already creates `/app/data` for the non-root user.

A local or Vite dev origin already on `CORS_ALLOW_ORIGINS` can send
cookies after unlock. Do not widen that list to `*`.

## Public speech budget

These routes reserve against the global call budget and the per-IP
request cap: `POST /api/ingest` (1 call), `POST /api/ingest/sample`
(2 calls: Timbre then Prisma), `POST /api/simulate` (1 call), `POST
/api/reply/{id}` (1 call), and the WebSocket at `/api/stream` (1 call reserved when
the session is admitted). Over the per-IP cap returns 429. A spent or
zero budget returns 503. Spent reservations are not refunded if the
upstream call later fails.

When Gnani itself returns a credit error, speech routes already answer
502/402-shaped upstream failures with no fabricated transcript.

## Storage

Free-host disk is ephemeral. A Space rebuild, a hardware recycle, or a
Render spin-down can delete `/app/data` even when a local restart on the
same machine does not. Do not claim the dispatch slate is durable, and
do not switch production back to an in-memory list to "fix" a wiped
Space. Events persist in SQLite at `RASTA_DB_PATH` across a local
restart on the same disk, but not across a host rebuild. A desk
operator can download a copy with `GET /api/admin/export` after
unlocking; that file is not an off-site backup (issue 35).

## Hugging Face Spaces (default)

Docker is not required on your laptop to open the Space; Spaces builds
the `Dockerfile` in this repository.

1. Sign in to [Hugging Face](https://huggingface.co) (this is the account
   login the maintainer has to complete; the repository only prepares
   the image and docs).
2. Create a new **Space**: SDK **Docker**, hardware **CPU basic** (free),
   visibility **public**.
3. Connect this GitHub repository, or push the same tree, and let Spaces
   build the root `Dockerfile`.
4. In the Space **Settings → Secrets**, add at least:
   - `GNANI_API_KEY`
   - `DISPATCH_PASSCODE`
   - `LLM_PROVIDER` (`rules`, or `groq` / `gemini` plus the matching key)
5. Optional secrets, if you need to override image defaults:
   `RASTA_ALLOWED_HOSTS`, `RASTA_DEMO_SPEECH_BUDGET`,
   `RASTA_PER_IP_REQUESTS_PER_MINUTE`, `RASTA_TRUST_PROXY_HEADERS`,
   `RASTA_DB_PATH`, `GROQ_API_KEY`, `GEMINI_API_KEY`.
6. Wait for the build. Open the Space URL. Check `GET /api/health`
   and `GET /api/ready` return JSON, `GET /` returns the desk HTML, and a missing key yields
   503 on `/api/ingest/sample`. With the key set, a noisy sample should
   return `customer_unreachable`, order `18`, and a Prisma `request_id`.
7. Paste that public HTTPS URL at the top of this file and commit it.
8. After issue 07, confirm the Talk path in a **secure context**
   (HTTPS). The image health check and operator probes use `/api/ready`.

### What you must do by hand

The image, docs, rate limits, and health check are in this repository.
The following still need the Hugging Face (or Render) account:

- create the public Docker Space (or the Render web service)
- set the secrets listed above in the host's secret store, never in git
- confirm the first build, copy the HTTPS origin into the URL line above
- optionally lock or pause speech by setting `RASTA_DEMO_SPEECH_BUDGET=0`

## Render (backup only)

If Spaces rejects the repository, create a free Render **web service**
from this repo. The start command can stay the image entrypoint: it
already honours `$PORT`. Set the same secrets as above, plus
`RASTA_ALLOWED_HOSTS` to your `*.onrender.com` hostname (and
`localhost,127.0.0.1` for the health check if you run one inside the
container). Keep `RASTA_TRUST_PROXY_HEADERS=true`.

## Local production-mode check (no Docker)

This environment could not run `docker build`. A local stand-in:

```bash
cd frontend && npm ci && npm run build && cd ..
export RASTA_ENV=production
export DISPATCH_PASSCODE=  # set in the shell, do not commit it
export RASTA_ALLOWED_HOSTS=localhost,127.0.0.1
export CORS_ALLOW_ORIGINS=
export RASTA_STATIC_DIR=frontend/dist
export PATH="/path/to/venv/bin:$PATH"
export PYTHONPATH=gnani_client:backend
uvicorn rasta.main:app --host 0.0.0.0 --port 7860 --workers 1
curl -s localhost:7860/api/health
curl -s -o /dev/null -w "%{http_code}\n" localhost:7860/
```

Pass `GNANI_API_KEY` from the shell the same way (`-e` if you later run
Docker). Never bake it into the image. `docker run --rm rasta ls -a`
must not show a `.env`; the Dockerfile never copies one.

## Passcode rotation

1. Choose a new `DISPATCH_PASSCODE`.
2. Update the secret in the Space (or process) environment.
3. Restart the app so it loads the new value. On Spaces this is a
   restart; the previous cookie signatures fail closed.
4. Dispatchers must unlock again from the slate.

After five wrong unlock attempts from one address inside the window, the
unlock route returns 429 until the window expires.

## Health and readiness

`GET /api/health` is the cheap liveness probe: the process is up. It
returns `ok`, `gnani_key_set`, and `llm_provider` only. It does not
touch disk, the event store, a credit budget, or Gnani.

`GET /api/ready` is readiness, for operators, the issue 24 smoke, and
the image `HEALTHCHECK`. It reports `gnani_key_set`, `db_writable`,
`rate_limit`, `demo_credits_remaining`, `demo_credits_exhausted`,
`schema_version`, `circuit_breaker`, and `events_in_store`.
`rate_limit` and the credit fields come from issue 13's process
speech guard. `db_writable` is a cheap write probe of `RASTA_DB_PATH`,
`schema_version` is `EventStore.schema_version()` (currently `2`), and
`events_in_store` is the number of rows in that store.
`circuit_breaker` is a snapshot of the issue 29 breakers
(`gnani_stt`, `gnani_tts`, `llm`), each `closed`, `open`, or
`half_open`. This process does not invent a second budget or a
shadow database.

HTTP 200 means the process should stay in rotation. A missing Gnani
key or a spent credit budget stays 200: speech routes already return
503, and the payload shows `demo_credits_remaining: 0` and
`demo_credits_exhausted: true` when the budget is exhausted. HTTP
503 with `ok: false` is reserved for a configured durable store that
cannot be written, opened, versioned, or counted, so the host can take
the process out of rotation. Those 503 responses still return the
structured ready body (`schema_version` or `events_in_store` may be
`null`). Neither payload includes `DISPATCH_PASSCODE`,
`GNANI_API_KEY`, or any other raw secret.

## Rollback

Redeploy the previous git tag or commit on the Space (or Render
service). There is no in-repo CD yet; issue 33 covers that wiring. The
free host has no durable disk, so rolling back the image does not
restore a wiped SQLite file.

## Credits and rate limits in the runbook

Issue 34 will own a longer operator runbook. Until then: set
`RASTA_DEMO_SPEECH_BUDGET=0` to pause public speech immediately, and
raise or lower the budget and per-IP cap as Space secrets, then restart.

## Checked revisions and manual rollback

Before publishing a revision, require its `container` job from
`.github/workflows/cd.yml` to pass. That job builds the Dockerfile, checks
the keyless non-root image and scans it with Trivy for HIGH/CRITICAL
vulnerabilities. The image's Python runtime versions come from
`requirements-runtime.lock`; the frontend uses its committed npm lock.

The workflow also runs on `v*` tag pushes and can be dispatched manually
from main. Tag/manual runs stop at the built-and-scanned image and a
handoff summary. They do not publish an image, update a host, create a
release or read provider/host credentials. Deploy the exact checked
revision through the host steps below, keeping secret values in its
secret store. Record the actual public URL and final revision after
verifying health, desk authentication and the public live smoke.

For rollback, retain the previous verified tag or full commit SHA before
updating a host. Restore that revision through the same host build path,
preserve the current secret configuration, and rebuild. Repeat health
and desk checks before the live smoke; record the restored revision,
time and result. Free-host local disk can be ephemeral, so code rollback
is not a database restore. A rollback is unverified until those checks
have actually run against the public origin.
