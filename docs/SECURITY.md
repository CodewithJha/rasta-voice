# Security and data handling

This is the current state at `3383f28`, not a production-security claim. Read
[ARCHITECTURE.md](ARCHITECTURE.md) and the
[production-readiness register](PRODUCTION_READINESS.md) before publishing a
demo URL. The unresolved controls below matter even with synthetic data.

Keep `GNANI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` and future
`DISPATCH_PASSCODE` values in environment variables or host secret settings.
The API loads a local `.env` without overriding real environment variables;
`.env` is ignored by git. Never place filled values in commits, image layers,
frontend bundles, URLs, screenshots, recordings, logs or issue comments.
`.env.example` contains names and empty secret values only. Browser clients
call our API; the server authenticates to speech providers. If a key leaks,
revoke/rotate it at the provider and update the host secret; deleting a git
line alone does not revoke a credential.

## Controls implemented now

- Uploads have a 2 MB read/ingest ceiling. The simulate route checks it before
  decoding or mixing. Only supported mono-compatible 16-bit PCM WAV inputs
  can enter that simulation path; broader content/duration validation is not
  a completed production control.
- Reply generation is limited locally to six requests/minute per direct
  client address, one in-flight upstream reply call and a 15-second HTTP
  timeout, with no automatic speech retries. Cache entries expire after ten
  minutes and are bounded by 128 entries / 8 MB of base64 audio. A missing
  key cannot use old cached replies. Client-supplied speech text is ignored.
- Streaming checks the WebSocket `Origin` against `CORS_ALLOW_ORIGINS` and
  enforces configured concurrent slots, frame/queue bounds and session/idle
  deadlines. Its generic admission hook currently allows requests; it is
  not an implemented shared credit budget.
- HTTP CORS uses the configured exact origin list. CORS and a WebSocket
  Origin check are browser boundaries, not authentication for direct API
  callers. A shared reverse proxy can also make the reply limiter see one
  client address; trusted forwarding policy is not yet implemented.
- UI text is set through text content rather than treating transcripts or
  provider replies as HTML. Emergency wording makes no unverified dispatch
  promise. This does not make automated extraction a safety authority.

## Controls still pending

Issue 13 owns deployment-wide per-IP limits and a global speech credit
budget across upload, sample, simulation, reply and streaming. Those limits
are not present on every route today. A REST sample uses two Gnani calls;
a new confirmation uses another; live streaming is also billable. Local
reply caching and stream slot limits do not bound the whole account's spend.
The backend currently maps a Gnani 402 to 502 with `upstream_status: 402`;
the rider shows credit exhaustion distinctly. There is no automatic billing
balance query or global public-demo pause switch yet. Do not infer that a
200 health response means credits or public abuse protection are available.

Desk authentication is issue 20. `GET /api/events` is currently public and
unprotected: setting `DISPATCH_PASSCODE` today does not enable an unlock
route, cookie or header check. The planned implementation must use timing-safe
comparison, an appropriately protected session/header mechanism, lockout and
CSRF defenses while leaving rider speech routes accessible under their spend
limits. None of those future controls is claimed as shipped here.

Issue 27 owns CSP, security headers, broader input/Origin hardening and CSRF
protection where relevant to the passcode session. The current app does not
install a CSP/security-header middleware. Issue 21 owns structured redacted
logging; current upstream warning logs can contain provider error messages.
Do not publish unreviewed log dumps. Issue 29 owns shared HTTP timeouts,
bounded retries and circuit breakers; reply's local timeout is not a global
resilience guarantee. Issue 22's readiness endpoint is still absent.

## Data policy

Repository audio, references and order tokens are synthetic. Do not upload
real customer calls, phone numbers, names, government IDs, delivery addresses
or real order records into git or a public demo. Real consented field audio
from issue 17 must remain outside the repository and be handled under that
issue's consent/deletion process. Simulated 8 kHz/G.711 audio is not evidence
of a real telephone channel.

The current store retains transcripts and extracted events in memory until
eviction or process restart. Capacity is configurable; it is not a timed
retention or secure deletion policy. SQLite persistence is issue 19;
redaction, retention TTL and explicit deletion are issue 28. An 8-digit run
is not promoted to an order id, but that check does not redact all PII from
transcripts, actions, responses or logs. Uploading audio sends it to Gnani;
choosing Groq/Gemini also sends transcript content to that provider.

## Reporting

Open a [GitHub issue](https://github.com/CodewithJha/rasta-voice/issues) with a
minimal synthetic reproduction, affected route and observed behavior. Never
paste an API key, passcode, session cookie, presigned URL or raw personal data.
For a leaked credential, revoke it first and report only that rotation was
required. There is no private security contact published by the team yet;
do not invent one or disclose sensitive exploit data in the public tracker.
