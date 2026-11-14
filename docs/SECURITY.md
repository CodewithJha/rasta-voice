# Security and data handling

Read [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) and the open issue
acceptance checks before publishing a demo URL. Passing tests is not proof of
a deployed host, field consent, available provider credit or production suitability.

Keep provider keys and `DISPATCH_PASSCODE` in environment variables or host
secret settings. `.env` is ignored by git. Never include filled credentials in
commits, image layers, browser bundles, URLs, screenshots, recordings or logs.
The server authenticates to providers; browser clients call our API. Rotate a
leaked key at its provider before updating host secrets. Removing a git line
does not revoke a credential.

## Dispatcher authentication and CSRF

Desk reads require a signed session cookie or a valid `X-Dispatch-Passcode`
header. Secret comparisons use constant-time digests. Failed unlocks and header
guesses share an atomic, process-local lockout per direct client address.

Browser unlock requires this sequence:

1. Fetch `GET /api/dispatch/csrf` with same-origin credentials. Its non-cacheable
   JSON contains `csrf_token`; an HttpOnly, SameSite=Strict cookie binds the
   challenge to this browser. The token is signed, purpose-separated and valid
   for five minutes. Refresh it after expiry or a successful unlock.
2. Send `POST /api/dispatch/unlock` with the JSON passcode, same-origin
   credentials and `X-Dispatch-CSRF: <csrf_token>`. Missing, altered or expired
   tokens fail before checking the body passcode. Successful unlock deletes
   the challenge cookie and sets the signed HttpOnly session cookie.
3. For subsequent writes, copy the readable `rasta_desk_csrf` cookie into
   `X-Dispatch-CSRF`. The server verifies both equality and its MAC bound to
   the current signed session actor. Tokens copied from another desk session
   cannot authorize this one.

All unsafe event, admin and dispatch routes, including versioned aliases,
share this guard. Browser Origin must match the request's exact origin when
present; cross-site or same-site Fetch Metadata is rejected. Non-browser
clients can perform the challenge flow or supply a valid custom passcode
header. Merely supplying an arbitrary header is not a CSRF bypass. Keep this
header out of public HTML, URLs, logs and screenshots.

Cookies use Secure on HTTPS, on trusted forwarded HTTPS and in production.
Forwarded scheme headers are ignored unless the trusted-proxy setting is
explicitly enabled. Desk authentication does not authenticate public rider
speech or substitute for spend limits.

## Request and browser boundaries

- [UPLOADS.md](UPLOADS.md) documents raw request and file size ceilings,
  duration/container validation, memory-only multipart handling, safe filenames
  and cleanup. Oversized bodies are bounded before multipart parsing. The
  simulation route additionally requires its supported PCM WAV format.
- Response policy covers normal responses, middleware denials and unhandled
  errors: CSP restricts resources to self, with Blob audio/worklet allowances;
  framing is denied, MIME sniffing disabled and referrers suppressed. HSTS is
  present on HTTPS and production responses. Production disables generated
  API documentation. Trusted Host and exact CORS/stream Origin checks apply.
- UI transcripts and provider replies are rendered as text. Emergency wording
  does not promise an unverified dispatch response. Extraction is not a safety
  authority.
- Speech routes share admission/concurrency limits, configured budgets and a
  pause switch. Samples and simulations can use multiple paid operations;
  upstream resilience permits bounded retries. See configuration, the smoke
  budget and [RUNBOOK.md](RUNBOOK.md) before enabling public speech.
  Process-local limits are not a provider account balance or distributed quota.
- Readiness and redacted request-ID logging help operations. A health/readiness
  200 does not establish usable credit or correct deployment permissions.
  Never publish unreviewed logs. The API contract and privacy integrations have
  separate acceptance checks in issues 26 and 28.

## Data policy and remaining acceptance

Repository audio, references and order tokens are synthetic. Real consented
field audio from issue 17 must stay outside git and public demos and follow
its consent/deletion process. Simulated telephone audio is not evidence from
a real telephone channel. Uploading audio sends it to Gnani; selecting an
external extraction provider also sends transcript content to that provider.

Events persist in SQLite. Privacy issue 28 covers transcript redaction,
retention TTL, export and deletion. Its PR review includes expired-event
transitions; do not claim acceptance until those paths and integration with
memory-only uploads are verified. An order-token heuristic alone does not
redact personal data. Hosting, private field evidence, a real public smoke,
owner-side branch settings and submission evidence remain separate gates.

## Reporting

Open a [GitHub issue](https://github.com/CodewithJha/rasta-voice/issues) with a
minimal synthetic reproduction, affected route and observed behavior. Never
paste credentials, session cookies, presigned URLs or raw personal data. For
a leaked key, rotate it first and report only that rotation was required.
No private security contact is published; do not invent one or disclose
sensitive exploit data in the public tracker.
