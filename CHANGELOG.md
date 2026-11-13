# Changelog

Notable changes are recorded here using Keep a Changelog categories. There is
no tagged release yet. Package version strings do not establish a release.
Move entries into a dated version section when issue 33 creates that tag.

## [Unreleased]

### Added

- Real Gnani Prisma transcription and streaming, with a rules/Groq/Gemini
  extractor and the frozen rider-event contract.
- Bounded in-memory event history and strict-after event polling API (PR 39).
- Deterministic synthetic noise and phone-quality benchmark preparation
  (PRs 40, 41 and 43).
- Timbre confirmations with bounded process caching and duplicate-request
  protection (PR 45). New uncached replies consume speech credits.
- Rider clean/noisy sample and upload controls with visible reply text (PR 46).
  A REST sample starts two logical speech operations; server retries can
  increase provider attempts and consume additional budget.
- Ordered dispatch tape with polling, backoff and a server-confirmed cursor
  that preserves unseen remote events (PR 47).
- Resumable five-configuration Prisma batch runner (PR 48). Uncached runs
  require a declared budget and rate. PR 73 publishes the completed live
  400-evaluation comparison, with cross-script WER and synthetic-data caveats.
- Architecture, security and contributor guides (PR 49), plus operations,
  governance, conduct, license and decision records.
- File-backed SQLite with migrations and protected snapshot export (PR 75),
  desk passcode/cookie authentication and request-correlated JSON logs.
- Production non-root image and free-host instructions (PR 71), readiness
  checks (PR 74), and image build/smoke/vulnerability gates (PR 76).
- Python type/coverage, frontend/browser and supply-chain gates; bounded keyless
  k6 scenarios and CI threshold-failure checks (PRs 79 and 80).
- Shared upstream client, operation-specific timeouts, bounded retries with
  jitter/Retry-After, circuit breakers and shutdown drain (PR 77). Speech retries
  reserve additional budget and do not establish the provider's exact bill.

### Fixed

- Upload size is bounded before noisy simulation allocates a mixed clip (PR 46).
- Smoke credit reporting includes server retries and derives its bound from an
  operator-supplied verified cap, defaulting conservatively to six attempts
  for one sample; preflight/keyless paths remain zero (PR 81).

### Known limitations

- The public HTTPS origin, public speech smoke and host rollback remain unverified.
- Free-host disk can disappear; process restart resets rate/budget controls.
- Dispatcher workflow (25), API contract/idempotency (26), broader security
  hardening (27) and retention/deletion (28) are not merged at this checkpoint.
- Local load and synthetic benchmark results do not prove public-host latency,
  live speech latency or consented field performance. No tagged release exists.
