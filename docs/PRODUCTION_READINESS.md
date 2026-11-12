# Rasta Voice — production readiness

**Verdict (12 Nov 2026):** the repo on `main` is a well-structured skeleton, not a production app. Merging issues 01–24 as they stood would produce a strong, demo-ready contest MVP with some production-minded hardening (SQLite, a desk passcode, JSON logs, a ready probe, rate limits, a smoke script, and a docs pack). It would still not be production-ready. Missing, among other things: a dispatcher ack/resolve workflow, SOS escalation, an audit trail, privacy TTL and a deletion path, security headers and CSRF, secret and dependency scanning, retries and a circuit breaker, schema migrations, a consistent error envelope, frontend tests, type and coverage gates, a production container, and a runbook. There is also no LICENSE.

This register is the honest gap list against a **single-instance, free-host, production-grade** bar: secure, private, reliable, observable, tested, operable, and complete for the delivery-driver use case, using only free tools and real Gnani APIs. It is not a multi-region, multi-tenant, or paid-APM bar. Those stretches are listed as P2 and sit on issue 35 (`day:post-contest`).

Issues 25–34, plus the production sections on existing issues, close the P0 and P1 rows. P2 rows that cannot fit before **15 Nov 2026, 18:00 IST** are marked post-contest.

## Definition of done

The app may be called production-ready for this project when every box is true:

- [ ] Every P0 row in this register is closed by a merged issue, with the tests named in that issue passing in CI.
- [ ] Public deploy (issue 13) serves HTTPS, uses host secrets, runs as a non-root container with a health check, enforces the passcode on the desk, and enforces rate and credit limits. `/api/health` and `/api/ready` tell the truth.
- [ ] A dispatcher can acknowledge, resolve, and escalate a drop, including an `accident_sos`, with an audit trail and a synthetic actor token. The Timbre accident line never claims help is on the way until an acknowledgement exists (issues 08, 25).
- [ ] Transcripts have a TTL, a deletion path, and phone-like digit redaction. Audio is not written to disk. (Issue 28.)
- [ ] Security headers, a tight CSP with self-hosted fonts, CSRF protection on the desk cookie, upload validation, and lockout on the unlock route are in place (issues 20, 27).
- [ ] Gnani and LLM calls use a shared HTTP client, timeouts, bounded retries with jitter, a circuit breaker, and they do not block the event loop. In-flight work drains on shutdown (issue 29).
- [ ] Errors use one JSON envelope that includes `request_id`. Ingest supports an idempotency key so a double click does not spend credits twice (issues 21, 26).
- [ ] CI runs lint, typecheck, tests with a coverage floor, secret scanning, dependency audit, a Docker build, and image scanning. No secrets in the logs or the image (issues 32, 33).
- [ ] `docs/SECURITY.md`, `docs/CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/RUNBOOK.md`, and a `LICENSE` exist and match the merged code (issues 23, 34).
- [ ] Contest rules still hold: synthetic data only, real Gnani APIs only, no mock mode in app code, free tools only, posts and the form in on time (issues 16, 18).

P1 boxes (Playwright, k6, i18n, Lighthouse, OpenAPI export, admin usage view, Dependabot, PR template) should also be merged before the deadline if time allows. They are not an excuse to slip the public video or the form.

## How to read the table

Severity:

- **P0** — must land before the app is called production-ready, and before a public URL is shared widely.
- **P1** — should land in the same window with the time we have; a truthful demo can ship if one of these slips, but the row stays open.
- **P2** — real production work that does not fit this deadline, or that a single free host cannot honestly provide. Issue 35.

Citations are to the tree at `866712c` unless a later issue already names the fix. "Planned in #N" means the issue exists but the code is not on `main` yet, and the production section may still extend it.

## Architecture

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| ARCH-01 | `POST /api/ingest` is `async` but calls synchronous `ingest()`, and `/api/ingest/sample` is fully sync (`backend/rasta/main.py` lines 50–68). Both wait on Gnani inside the event loop. | One slow Prisma call stalls health checks, the slate poll, and every other rider. | P0 | 29 |
| ARCH-02 | `PrismaSTT`, `TimbreTTS`, and `PrismaBatch` each open a new `httpx.Client(timeout=60.0)` per call (`gnani_client/gnani_client/stt.py` line 139, same pattern in `tts.py` and `batch.py`). | No connection reuse, no central timeout policy, hard to attach retries or a breaker. | P0 | 29 |
| ARCH-03 | Config is raw `os.environ` in `main.py`, `extract.py`, and `gnani_client/env.py`. There is no typed settings object and no boot-time validation. | A typo in an env name becomes a 503 in production, or a silently wrong default. | P1 | 13, 29 |
| ARCH-04 | The only documented topology is one uvicorn worker (`docs/issues/04-event-store.md`, `#13`). That is correct for the free host, but it is not written down as a production constraint. | Someone will scale `--workers` and then share neither the SQLite lock nor in-process rate limits. | P1 | 13, 34 |
| ARCH-05 | `RiderEvent` is frozen (`additionalProperties: false` in `shared/rider_event.schema.json`, `extra="forbid"` in `backend/rasta/schema.py`). Lifecycle, actor, and extractor source cannot be added inside `event`. | If later issues stuff new fields into `event`, clients and the schema drift test break. | P0 | 02, 25, 26 |
| ARCH-06 | Rider, dispatch, and admin share one unauthenticated app with no route groups or policy module. | Easy to attach a new desk route and forget the passcode. | P1 | 20, 25, 27 |

## Config and secrets

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| CFG-01 | `.env.example` lists only `GNANI_API_KEY`, `GNANI_BASE_URL`, `LLM_PROVIDER`, and the two LLM keys. It does not list `RASTA_DB_PATH`, `DISPATCH_PASSCODE`, timeouts, budgets, CORS origins, or log level. | Operators will boot a public Space missing the passcode or the budget. | P1 | 13, 19, 20 |
| CFG-02 | No settings validation at process start. `load_dotenv()` runs at import (`main.py` lines 17–18). | Tests and deploys can pick up a leftover `.env`. Invalid values are not caught at boot. | P1 | 13 |
| CFG-03 | No dev / staging / prod split. CORS is hardcoded to the Vite dev origins (`main.py` lines 31–36). | A production deploy either cannot be called from its own host if you keep a split frontend, or someone sets `allow_origins=["*"]`. | P0 | 13, 27 |
| CFG-04 | Runtime deps are lower-bounded only (`fastapi>=0.115`, `vite ^6.0.0` in `backend/pyproject.toml` and `frontend/package.json`). | A bad upstream release can break the desk on a clean install. | P1 | 33 |
| CFG-05 | There is no secrets policy in the repo yet (`docs/SECURITY.md` is issue 23). Gitignores `.env` (good). | New keys added in later issues may be logged or baked into the image. | P0 | 13, 21, 23, 33 |

## Security

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| SEC-01 | No `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, or `Permissions-Policy` middleware. | XSS, MIME sniffing, and unwanted mic/camera access have no browser backstop. | P0 | 27 |
| SEC-02 | CORS is localhost-only today, with `allow_methods=["*"]` and `allow_headers=["*"]` (`main.py` lines 29–37). Issue 13 serves the UI same-origin, which is the right default, but nothing pins that or forbids a wildcard later. | A sloppy CORS change on a public API is credential theft on the desk cookie. | P0 | 13, 27 |
| SEC-03 | Every route is public. Issue 20 adds a shared passcode, not per-user auth, and as written it has no CSRF check, no unlock lockout, and no rotation story. | On a public URL the slate leaks every transcript. A CSRF post can unlock or ack if we add cookies without a token. | P0 | 20, 27 |
| SEC-04 | `/api/ingest` reads the whole upload into memory (`main.py` lines 50–52). The only limit is 2 MB after the read (`pipeline.py` lines 8, 32–33). Content type and duration are not checked; `Path.name` is the only filename hygiene (`stt.py`). | A non-audio bomb, a huge "WAV", or a crafted name wastes memory and credits. | P0 | 27 |
| SEC-05 | `_guard` returns `detail` as a string for some errors and as a dict for 502 (`main.py` lines 73–88). Upstream bodies can be forwarded in `GnaniError`. | Clients cannot parse errors reliably; upstream text may leak. | P1 | 26 |
| SEC-06 | CI (`.github/workflows/ci.yml`) has no secret scanning. | A key committed in a PR can reach `main` and the public repo. | P0 | 33 |
| SEC-07 | No `pip-audit`, `npm audit`, or Dependabot. | Known vulnerable FastAPI/Vite/httpx releases will sit unnoticed. | P0 | 33 |
| SEC-08 | No SAST (`bandit` or equivalent; ruff is style/bug lint only). | Common Python footguns (assert on secrets, bind to all interfaces with debug) are not gated. | P1 | 33 |
| SEC-09 | Actions are floating tags (`actions/checkout@v4`, `setup-python@v5`, `setup-node@v4`). | A compromised tag can run in CI with repo permissions. | P1 | 33 |
| SEC-10 | `frontend/index.html` lines 7–12 load Atkinson, Fraunces, and Martian Mono from Google Fonts. | Third-party requests break a tight CSP, leak visitor IPs, and fail on a bad network. The licences allow self-hosting. | P0 | 27, 30 |
| SEC-11 | No rate limit or credit budget in code. Planned in issue 13; until then a public **Speak a sample line** button is an open credit drain (two Gnani calls per click). | The contest grant can be exhausted in minutes. | P0 | 13 |
| SEC-12 | FastAPI's `/docs` and `/redoc` will be public on the Space. | Extra attack surface and a noisy signal that the API is unauthenticated. | P1 | 27 |
| SEC-13 | No trusted-host check and no HTTPS redirect at the app (the host may terminate TLS). | Host-header tricks and mixed-content cookie flags. | P1 | 13, 27 |
| SEC-14 | Planned `WS /api/stream` (issue 07) is a public, credit-consuming socket. The current 07 text budgets it only by referring out to 13. | One open socket can burn the grant and pin a worker. | P0 | 07, 13, 27 |
| SEC-15 | No `CODEOWNERS`, PR template, or documented branch protection. | Accidental reviews, and `main` can be force-pushed. | P1 | 33, 34 |

## Privacy and data retention

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| PRIV-01 | No store on `main`. Issue 19 persists events in SQLite and caps at 200, which is capacity, not retention. There is no TTL. | Transcripts of even synthetic speech sit on disk until a rebuild or the cap evicts the oldest, including SOS text. | P0 | 19, 28 |
| PRIV-02 | No deletion path for an event or for "all desk data". | An operator cannot honour a "wipe this desk" request, or recover from a bad paste. | P0 | 28 |
| PRIV-03 | The rules extractor refuses 8+ digit tokens as `order_id` (`backend/rasta/extract.py`, `_LONG_DIGITS`) but leaves them in `transcript`. | A spoken phone number is stored and then shown on the slate. | P0 | 28 |
| PRIV-04 | Audio is not written to disk today (good). Nothing tests that simulate, reply, or stream will not start logging wavs "for debug". | A later debug flag can put rider audio in the image or the Space. | P1 | 28, 21 |
| PRIV-05 | No access log of who read a transcript (issue 20 is one shared passcode). | You cannot tell which dispatcher opened an SOS. | P1 | 25, 28 |
| PRIV-06 | Issue 17 keeps field recordings out of git. The running app has no written data-classification rule. | Easy to upload a real call "just to test". | P1 | 17, 28, 34 |

## Reliability

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| REL-01 | Clients do one POST and raise (`stt.py` lines 128–136). No retry, no backoff, no jitter. | A single 429 or blip fails the rider and still spent a connection. Unbounded retries would also multiply credits (CON-03). | P0 | 29 |
| REL-02 | No circuit breaker around Gnani or the LLM. | A down upstream turns every click into a long timeout and a 502. | P0 | 29 |
| REL-03 | The only timeout is 60 seconds per client. Issue 02 adds an LLM timeout; issue 08 has none. There is no per-route deadline. | A stuck call holds a worker for a minute. | P0 | 02, 08, 29 |
| REL-04 | `/api/ingest` and `/api/ingest/sample` are not idempotent. The rider page will retry or double-click (`frontend/src/rider.ts` lines 72–78 have no disable-until-done today; issue 09 adds a loading state). | Double spend of Timbre + Prisma credits, duplicate desk rows. | P0 | 09, 26, 29 |
| REL-05 | `lifespan` in `main.py` lines 22–25 only logs a missing key. No graceful shutdown, no close of HTTP or SQLite. | Deploy rolling and local Ctrl-C drop in-flight calls and can leave a WAL journal dirty. | P0 | 29, 19 |
| REL-06 | Issue 07's audit covers live pumping and cleanup, but not pings, a hard 15-minute session cap, a cap on concurrent sockets, or origin checks. | Leaked sockets and hung worklets. | P0 | 07, 29 |
| REL-07 | Upstream 429/402 today become 502 (`main.py` lines 84–88, `test_ingest.py`). | The rider and the limiter cannot tell "slow down" from "Gnani is broken". | P1 | 26, 29 |
| REL-08 | `POST /api/reply/{id}` (issue 08) will call Timbre on every play. | "Hear dispatch" twice is two TTS credits. | P1 | 08, 26 |

## Data layer

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| DATA-01 | Issue 19 introduces SQLite with no schema version and no migrations. | The second column you add will crash a Space that already has a file. | P0 | 19 |
| DATA-02 | Indexes, `busy_timeout`, and WAL are optional or unspecified in 19. | `since` polls and concurrent ingest+ack will lock or scan. | P1 | 19 |
| DATA-03 | No backup or restore, and free-host disk is ephemeral (already noted in 19). | A Space rebuild wipes the desk; there is no export for operators. | P1 | 19, 34, 35 |
| DATA-04 | The cap of 200 silently drops the oldest (issues 04 and 19). | An SOS can vanish without a trace. | P1 | 19, 28 |
| DATA-05 | No event lifecycle columns (state, actor, version). | Ack/resolve cannot be stored without breaking the frozen `event` object (ARCH-05). | P0 | 19, 25 |

## API design

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| API-01 | Routes are `/api/...` with no version. Changing a contract later breaks the UI and the smoke script. | Production APIs need a compatibility story. | P1 | 26 |
| API-02 | Error bodies are inconsistent (SEC-05) and have no `request_id`. | Operators cannot match a failed click to a log line. | P0 | 21, 26 |
| API-03 | OpenAPI is FastAPI's default, unreviewed, and will be public (SEC-12). There is no exported reference. | Judges and operators have no stable contract; attackers get a map. | P1 | 26, 27 |
| API-04 | `GET /api/events?since=` (issue 04) has no limit or page token. After 200 rows, or with a busy desk, the first payload is large. | Slow slate, extra work on every full refresh. | P1 | 26 |
| API-05 | No `Idempotency-Key` on credit-spending POST routes (REL-04, REL-08). | Duplicate spends. | P0 | 26 |
| API-06 | No pagination or ETag / `If-Match` for updates. | Two dispatchers will overwrite each other once ack exists. | P1 | 25, 26 |

## Observability

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| OBS-01 | `logging.getLogger("rasta")` is unconfigured; 502s log a warning (`main.py` lines 19, 85). Issue 21 adds JSON logs and `X-Request-ID`. Until then there is no request correlation. | You cannot debug a failed demo after the fact. | P0 | 21 |
| OBS-02 | No metrics endpoint (latency, in-flight, Gnani calls, credits, errors). | Capacity and credit burn are invisible. | P1 | 25, 22 |
| OBS-03 | No distributed tracing. | Hard to see whether a slow ingest was Timbre, Prisma, or the LLM. Acceptable to skip on one process if logs carry ids and latency (issue 21). | P2 | 35 |
| OBS-04 | No error-tracking product. A self-hosted GlitchTip would not fit this host and deadline honestly. | P1 is in-process error counts on `/api/ready` and the admin view. P2 is a real tracker. | P1 / P2 | 22, 25, 35 |
| OBS-05 | No SLOs, dashboards, or alerting. | A silent 502 loop or an exhausted grant is noticed by a judge, not by us. | P1 | 25, 34 |
| OBS-06 | Issue 22's ready probe does not yet exist, and as specified it does not report breaker state or migration version. | A stale schema or an open breaker looks "ready". | P1 | 22 |

## Performance

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| PERF-01 | Event-loop blocking (ARCH-01) and a new client per call (ARCH-02). | Tail latency and stalled polls. | P0 | 29 |
| PERF-02 | No load test and no latency budget. | We will not know whether the desk survives three judges clicking at once. | P1 | 31 |
| PERF-03 | No in-process concurrency cap on Gnani calls besides the issue 13 budget. | A burst can queue 60s timeouts and blow the grant. | P0 | 13, 29 |
| PERF-04 | Uploads are fully buffered (SEC-04). | Memory spikes on the 2 MB boundary. Acceptable if the cap is enforced *before* a 2 MB read, via Starlette's max body size. | P1 | 27 |

## Testing

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| TEST-01 | CI runs `pytest` with no coverage floor (`.github/workflows/ci.yml` line 20). | New code can land untested. | P1 | 32 |
| TEST-02 | No frontend unit tests. `npm run check` is `tsc --noEmit` only (`frontend/package.json`). | Issue 09/10/30 UI can regress without a red CI. | P1 | 32 |
| TEST-03 | No browser e2e. Issue 24 is a Python smoke script, not a UI test. | Mic, passcode cookie, and 360 px layout are manual only. | P1 | 32, 24 |
| TEST-04 | Contract tests check Pydantic field names vs the JSON schema and vs TypeScript strings (`backend/tests/test_schema.py`). They do not check the ingest envelope or OpenAPI. | Envelope fields (`id`, `extractor_source`, `state`) will drift. | P1 | 26, 32 |
| TEST-05 | No `mypy` or `pyright` in CI. Frontend `strict` is already on (good). | Optional types and dict envelopes hide bugs. | P1 | 32 |
| TEST-06 | k6/locust are not in the plan. | PERF-02. | P1 | 31 |

## Frontend

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| FE-01 | The chit prints raw JSON (`frontend/src/rider.ts`). Issues 09/10 improve layout but not a judged, human event view. | A production rider screen is not a debug dump. | P1 | 09, 30 |
| FE-02 | All strings are hardcoded English (with some Hinglish copy planned). `index.html` is `lang="en"`. No message catalogue. | The product is Hinglish-first; a locale toggle is part of quality, not decoration. | P1 | 30 |
| FE-03 | `fetch` has no timeout, retry, or offline message (`rider.ts` `post()`). | A slow network looks like a hang. "On the line…" never ends. | P1 | 09, 30 |
| FE-04 | No window-level error handler. `main.ts` throws if `#app` is missing, then nothing. | A runtime exception blanks the desk during a demo. | P1 | 30 |
| FE-05 | Mic permission UX is only in issue 07. Slow worklet, no secure-context warning, no device-busy state beyond a `<pre>` line. | HTTPS-only `getUserMedia` will fail silently on a mistaken HTTP origin. | P1 | 07, 30 |
| FE-06 | No Lighthouse or bundle budget. Google Fonts block first paint (SEC-10). | Outdoor rider use needs a fast, readable first load. | P1 | 30, 32 |
| FE-07 | Hardening on 09/10 covers 360 px, 4.5:1, and keyboard, but there is no WCAG AA pass (labels, live regions, reduced motion already partly in `styles.css`, file input is visually hidden). | A dispatcher using a keyboard or a screen reader cannot run the desk. | P1 | 09, 10, 30 |
| FE-08 | No production source-map policy. | Maps in a public Space leak source; no maps make production errors opaque. | P2 | 13, 35 |

## CI/CD

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| CICD-01 | CI is ruff + pytest + `tsc` only (`.github/workflows/ci.yml`). | Type, coverage, security, and container gates are missing. | P0 | 32, 33 |
| CICD-02 | No Docker build in CI, and no image scan. There is no Dockerfile on `main` yet (issue 13). | The first image that reaches a Space may be rootful and may contain `.env`. | P1 | 13, 33 |
| CICD-03 | No continuous deploy, no release tags, no changelog gate. | Production is a manual Space rebuild with no rollback tag. | P1 | 33, 34, 35 |
| CICD-04 | No Dependabot, PR template, or `CODEOWNERS` (SEC-15, SEC-07). | Supply chain and review quality. | P1 | 33 |

## Containerization

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| CTR-01 | No Dockerfile, no `.dockerignore`. Issue 13 drafts a multi-stage build but does not require a non-root user, a `HEALTHCHECK`, pinned base tags, or a read-only data path. | Root in a public Space, no probe for the host, floating `python:3.12-slim` tags. | P0 | 13 |
| CTR-02 | No discussion of `/tmp` vs `RASTA_DB_PATH` permissions for the non-root user. | The ready probe will 503 after we drop root if the path is not writable. | P1 | 13, 19, 22 |

## Operations

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| OPS-01 | No runbook. | At 17:00 IST on 15 Nov, nobody has a page that says what to do when Gnani returns 402. | P0 | 34 |
| OPS-02 | Issue 13/22 describe credit exhaustion in the API, not a human playbook (who pauses the public button, who rotates the key, what the post should say). | The public URL can sit in a 429 loop during judging. | P0 | 13, 22, 34 |
| OPS-03 | No rollback steps (previous image tag, previous commit on the Space). | A bad Day 3 deploy has no way back. | P1 | 13, 33, 34 |
| OPS-04 | No incident template (what to capture: request ids, ready payload, recent logs). | Issue 21's logs only help if someone knows to copy them. | P1 | 21, 34 |
| OPS-05 | No staging environment. | The first production deploy is the first shared environment. | P2 | 35 |
| OPS-06 | Feature flags: `LLM_PROVIDER` is a real selector, not a mock, which is correct. Nothing documents the rule "never add a mock flag". | A later "demo_mode" would violate contest rules and this register. | P1 | 23, 34 |

## Documentation

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| DOC-01 | No `LICENSE`. | The repo is public; nobody knows if a judge or a fork can reuse it. | P0 | 34 |
| DOC-02 | No `CHANGELOG`, no `CODE_OF_CONDUCT`. | Releases and conduct for a two-person public repo. | P1 | 34 |
| DOC-03 | No ADRs. Decisions (SQLite, shared passcode, frozen schema, no mock mode) live in issue text that will rot. | Future us will re-litigate them under deadline pressure. | P1 | 34 |
| DOC-04 | No written API reference besides default Swagger. | API-03. | P1 | 26, 34 |
| DOC-05 | `ARCHITECTURE.md`, `SECURITY.md`, and `CONTRIBUTING.md` are planned in issue 23 and are not in the tree. | Judges and operators have only the README and the issue folder. | P0 | 23 |
| DOC-06 | This register did not exist. | Production work had no single backlog. | P0 | this document |

## Product completeness

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| PROD-01 | The slate only displays the latest event (today) or a poll of a list (issue 10). There is no acknowledge or resolve action. | A desk that cannot close a drop is not a dispatch tool. | P0 | 25, 10 |
| PROD-02 | No lifecycle states (`new`, `acked`, `resolved`, `escalated`). | Operators cannot sort or filter work. | P0 | 25 |
| PROD-03 | One shared passcode, no dispatcher identity, no conflict check. | Two people on the desk will clash; the audit will say "the passcode". | P1 | 20, 25 |
| PROD-04 | No synthetic rider token. The chit is anonymous. | You cannot tell two riders apart on the slate. | P1 | 25 |
| PROD-05 | No audit trail of ingest, ack, resolve, unlock, or delete. | Safety and privacy reviews have nothing to read. | P0 | 25, 28 |
| PROD-06 | Accident is a prefix `SOS` in issue 10 and a spoken line in issue 08. There is no escalation path, ack SLA, or audible alert. | The one life-safety path in the product is a label. | P0 | 08, 10, 25 |
| PROD-07 | No admin view of credit spend, error rate, or store size. | We will hit 402 in public without warning. | P1 | 22, 25 |
| PROD-08 | Notifications: the slate is a poll, not a live region with sound for HIGH/SOS (issue 10 hardening asks for a live region). | A dispatcher looking at another window misses an accident. | P1 | 10, 25, 30 |

## Contest rules

| ID | Gap | Why it matters | Sev | Issue |
| --- | --- | --- | --- | --- |
| CON-01 | The skeleton and the 01–24 plan already honour synthetic data, real Gnani APIs, no mock mode, and free tools. Production work can still slip the video and the form if it grows without a cut line. | Missing the 15 Nov 2026, 18:00 IST form is an automatic loss, however complete the desk is. | P0 | 16, 18, PLAN |
| CON-02 | Retries, smoke tests, k6, and Playwright must not open a mock path in app code, and must not use paid SaaS. | A "demo mode" or a paid typography kit would break the rules. | P0 | every issue, 29, 31, 32 |
| CON-03 | Retries and double-clicks can multiply credit spend (REL-01, REL-04). | The grant can die during our own tests. | P0 | 13, 24, 26, 29, 31 |

## Counts

| Area | P0 | P1 | P2 | Total |
| --- | --- | --- | --- | --- |
| Architecture | 3 | 3 | 0 | 6 |
| Config and secrets | 2 | 3 | 0 | 5 |
| Security | 9 | 6 | 0 | 15 |
| Privacy | 3 | 3 | 0 | 6 |
| Reliability | 6 | 2 | 0 | 8 |
| Data layer | 2 | 3 | 0 | 5 |
| API design | 2 | 4 | 0 | 6 |
| Observability | 1 | 4 | 1 | 6 |
| Performance | 2 | 2 | 0 | 4 |
| Testing | 0 | 6 | 0 | 6 |
| Frontend | 0 | 7 | 1 | 8 |
| CI/CD | 1 | 3 | 0 | 4 |
| Containerization | 1 | 1 | 0 | 2 |
| Operations | 2 | 3 | 1 | 6 |
| Documentation | 3 | 3 | 0 | 6 |
| Product | 4 | 4 | 0 | 8 |
| Contest | 3 | 0 | 0 | 3 |
| **Total** | **44** | **57** | **3** | **104** |

Some P1/P2 cells are a single row with two severities (OBS-04); they are counted once, at the higher in-contest severity, and the P2 stretch is also listed under issue 35. The P2 column counts only rows whose *primary* close is post-contest (OBS-03, FE-08, OPS-05).

## Existing issues this register extends

02, 07, 08, 09, 10, 13, 17, 19, 20, 21, 22, 23, 24 — each has (or will have) a `<!-- rasta-voice-production-2026-11-12 -->` section. Contest issues 14–18 stay focused on the deadline; they are cited where a slip would break CON-01, not rewritten as platform work.

## New issues

25 dispatcher workflow; 26 API contract; 27 security hardening; 28 privacy and retention; 29 upstream resilience; 30 frontend production quality; 31 load tests; 32 quality gates; 33 CI/CD and supply chain; 34 operations and legal docs; 35 post-contest operations stretch.
