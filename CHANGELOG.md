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
  A REST sample synthesizes speech and transcribes it, costing two API calls.
- Ordered dispatch tape with polling, backoff and a server-confirmed cursor
  that preserves unseen remote events (PR 47).
- Resumable five-configuration Prisma batch runner (PR 48). Uncached runs
  require a declared budget and rate; completed live scores are still pending.
- Architecture, security and contributor guides (PR 49), plus operations,
  governance, conduct, license and decision records.

### Fixed

- Upload size is bounded before noisy simulation allocates a mixed clip (PR 46).

### Known limitations

- Restart clears event history; SQLite, desk authentication, readiness,
  production deployment and global speech budgets are still open work.
- No complete live benchmark comparison or production SLO claim is published.
