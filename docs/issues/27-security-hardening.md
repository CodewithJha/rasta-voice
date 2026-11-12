# 27 — Security hardening: headers, CSP, CSRF, uploads, CORS

- **Labels:** `area:app`, `day:3`, `security`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 3 (14–15 Nov 2026), after 13 and 20 so same-origin deploy and the desk cookie exist. You can land the header middleware earlier if you keep CORS defaults safe. Closes SEC-01, SEC-02, SEC-04, SEC-10, SEC-12, SEC-13, SEC-14, CFG-03, PERF-04, and the CSRF half of SEC-03.
- **Depends on:** issues 13 and 20. Coordinate font self-hosting with issue 30 (this issue must land self-hosted files so CSP can drop Google Fonts; 30 may restyle but must not add the CDN back).

## Description

Put a browser and an upload bar around the public demo.

Security headers on every HTTP response (including `/`, `/api/health`, and errors):

- `Content-Security-Policy`: default `self`; `script-src 'self'`; `style-src 'self'`; `font-src 'self'`; `img-src 'self' data:`; `connect-src 'self'`; `media-src 'self' blob:`; `worker-src 'self' blob:`; `frame-ancestors 'none'`; `base-uri 'self'`; `form-action 'self'`. No `unsafe-inline` unless you have a documented hash/nonce for a single inline hook and a test for it. `microphone` is allowed only via `Permissions-Policy`.
- `Permissions-Policy`: `microphone=(self)`, `camera=()`, `geolocation=()`, `payment=()`.
- `Referrer-Policy`: `no-referrer`.
- `X-Content-Type-Options`: `nosniff`.
- `X-Frame-Options`: `DENY`.
- `Strict-Transport-Security` when the request is HTTPS (or when `RASTA_ENV=prod`): `max-age=31536000; includeSubDomains`.
- Do not add `Access-Control-Allow-Origin: *`. Production default is same-origin (no CORS middleware, or an empty allow list). Dev keeps the Vite origins from `CORS_ALLOW_ORIGINS`. Credentials are never paired with a wildcard.

Self-host Atkinson Hyperlegible, Fraunces, and Martian Mono under `frontend/public/fonts/` (they are freely licensed). Remove the Google Fonts `<link>` tags from `frontend/index.html`. `@font-face` in CSS only. Check the licence files in that folder. No paid font.

CSRF: every state-changing desk route (`/api/dispatch/unlock`, ack/resolve/escalate, delete from issue 28) requires a CSRF token bound to the session cookie. Issue it on `GET /api/dispatch/csrf` (passcode already required except for the unlock GET/POST pair: unlock is special — use a double-submit token set on the first GET of the slate, or a synchronizer token in an `httpOnly` cookie plus a readable cookie/`X-CSRF-Token` header). `SameSite` on the passcode cookie stays `Lax` or `Strict` (issue 20). A test that posts ack with a valid passcode cookie and no CSRF token is 403.

Uploads:

- Enforce a maximum body size *before* buffering 2 MB (Starlette `max_upload_size` or equivalent). Oversize is 413 in the issue 26 envelope.
- Sniff WAV/MP3/OGG/FLAC/M4A magic; reject other payloads with 415 `unsupported_media_type`, even if the filename ends in `.wav`.
- Reject clips whose PCM duration is over 30 seconds (Prisma REST limit) with 413.
- Cap filename to a safe basename of 64 characters.

Other:

- Disable `/docs`, `/redoc`, and `/openapi.json` when `RASTA_ENV=prod` (issue 26's `docs/API.md` remains the reference).
- `TrustedHostMiddleware` with hosts from `RASTA_ALLOWED_HOSTS` in prod.
- `WS /api/stream` (issue 07) must check `Origin` against the same allow list, apply issue 13's budget, and cap concurrent sockets (issue 07 production section). A missing origin on a browser socket is a 403 close.

## Files to touch

- `backend/rasta/security.py` or `headers.py` (new)
- `backend/rasta/main.py` (middleware hookup, CORS from env, docs off in prod)
- `backend/rasta/pipeline.py` and the ingest route (upload checks)
- `backend/tests/test_security.py` (new)
- `frontend/index.html`, `frontend/src/styles.css` (or a fonts CSS), `frontend/public/fonts/*`
- `frontend/src/dispatch.ts` (CSRF header)
- `.env.example` (`RASTA_ENV=`, `CORS_ALLOW_ORIGINS=`, `RASTA_ALLOWED_HOSTS=`)
- `docs/DEPLOY.md` and `docs/SECURITY.md` if they already exist; otherwise describe the headers in the PR and leave the prose file to 23/34

## Do not touch

`gnani_client/`, `benchmark/`, the frozen schema. Do not re-open Google Fonts. Do not add a paid WAF or a paid traffic-filter product.

## Input / output contract

`GET /api/health` in prod includes the header set above. `Content-Security-Policy` does not contain `fonts.googleapis.com` or `unsafe-eval`.

`POST /api/ingest` with a 3 MB body is 413. A `text/plain` file named `clip.wav` is 415.

## Acceptance criteria

- [ ] Header tests on `/`, `/api/health`, and a 503 response.
- [ ] CSP on a built page allows the app to load, play a sample, and open a worklet, and forbids a script from `https://example.com` (a small unit test or a documented Playwright case in 32).
- [ ] `index.html` has no `fonts.googleapis` or `fonts.gstatic` reference. `rg fonts.googleapis frontend` is empty.
- [ ] CSRF: desk POST without a token is 403; with a token it succeeds. Rider ingest does not require CSRF.
- [ ] Upload tests: oversize, bad magic, over-long duration, ugly filename.
- [ ] `/docs` is 404 or 403 when `RASTA_ENV=prod`, and available when `RASTA_ENV=dev`.
- [ ] `pytest`, `ruff`, and `npm run check` pass.

## How to test

```bash
RASTA_ENV=prod pytest backend/tests/test_security.py -q
cd frontend && npm run build && npm run check
rg -n "fonts.googleapis|unsafe-eval" frontend
```
