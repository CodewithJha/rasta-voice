# 20 — Dispatcher passcode

- **Labels:** `area:app`, `day:2`, `api`, `security`
- **Owner:** Member B: app & realtime
- **Target day:** Day 2 (13–14 Nov 2026), after issue 10 has a working slate to protect.
- **Depends on:** issue 10. The rider page stays public. Issue 13's rate limits still apply to the public speech routes.

## Description

The dispatch slate and its APIs cannot stay open on a public URL. Anyone with the link would see every event and could poke desk routes. Protect them with one shared passcode from the environment, not a user database and not a paid auth vendor.

`DISPATCH_PASSCODE` is required for the desk to work. If it is missing or empty, `GET /api/events` and any later dispatch write or ack route answer 503 with a clear "DISPATCH_PASSCODE is not set" message, the same loud style as a missing `GNANI_API_KEY`. Do not fail open on a public host.

Check:

- Compare the presented secret to `DISPATCH_PASSCODE` with `hmac.compare_digest` on equal-length bytes (encode both, or hash both first so a length mismatch cannot early-return). Do not use `==` on the raw strings as the only check.
- Accept the passcode from an `httpOnly` cookie (preferred after unlock) or from a request header, for example `X-Dispatch-Passcode`. Cookie flags: `HttpOnly`, `Path=/`, `SameSite=Lax` (or `Strict`), and `Secure` when the request is HTTPS. No `document.cookie` read of the secret. Do not put the passcode in client JavaScript, in a frontend env file, or in logs, error details, or health payloads.
- `POST /api/dispatch/unlock` (or a close name) accepts a JSON body `{"passcode": "..."}`, sets the cookie on success, and returns 204 or a small `{"ok": true}`. Wrong passcode is 401. Do not echo the guess back.
- `GET /api/events`, `GET /api/events?since=`, and any dispatch ack or update route you add now or later require a valid cookie or header. 401 otherwise, with a short body the slate can display. Do not 302 to a different origin.
- Rider routes stay public: `POST /api/ingest`, `/api/ingest/sample`, `/api/simulate`, the page at `/`, and (once they exist) `/api/reply/{id}` and the rider websocket. They remain rate-limited and budgeted by issue 13. A rider must not need the passcode to speak a sample line.

Frontend, only `frontend/src/dispatch.ts` and `dispatch.css`:

- On 503 (passcode not configured) and on 401, show an unlock field on the slate, not on the rider chit. Submitting it calls the unlock route (same origin) and retries the list. Do not store the passcode in `localStorage` or in a JS constant.
- After a successful unlock, polls send cookies with `credentials: "same-origin"` (or `include` on the same origin). Confirm the Vite proxy forwards the cookie in dev.
- The rider column must keep working in the same tab if the desk is locked.

CORS: if you already allow the Vite dev origin, allow the passcode header and credentials only as needed, and do not widen `allow_origins` to `*`.

## Files to touch

- `backend/rasta/auth.py` or `backend/rasta/dispatch_auth.py` (new)
- `backend/rasta/routes_events.py` (guard the list; add unlock)
- `backend/rasta/main.py` only if the router or CORS needs a line
- `backend/tests/test_dispatch_auth.py` (new)
- `frontend/src/dispatch.ts`
- `frontend/src/dispatch.css`
- `.env.example` (add `DISPATCH_PASSCODE=` with a comment)
- `docs/DEPLOY.md` (list the secret next to `GNANI_API_KEY`)

## Do not touch

`frontend/src/rider.ts`, `frontend/src/styles.css`, `frontend/src/main.ts`, `benchmark/`, `gnani_client/`, `schema.py`. Do not add a third-party auth SDK.

## Input / output contract

`POST /api/dispatch/unlock` with `{"passcode": "<value>"}`:

- 204 or `{"ok": true}` plus `Set-Cookie` on a match.
- 401 on a mismatch. Body must not contain the passcode.
- 503 if `DISPATCH_PASSCODE` is unset.

`GET /api/events` with a valid cookie or `X-Dispatch-Passcode` header: same JSON as issue 04 and 19.

`GET /api/events` without it: 401.

`POST /api/ingest` and `POST /api/ingest/sample` without it: unchanged, still public.

## Acceptance criteria

- [ ] Missing `DISPATCH_PASSCODE` makes desk routes 503, not open.
- [ ] Wrong passcode is 401. Timing-safe compare is used.
- [ ] A test unlocks, reads `/api/events` with the cookie, and is denied without it. Another test uses the header. Tests set the env in the test process; they do not hard-code a production secret.
- [ ] The passcode string does not appear in frontend source, logs, or error JSON. A test (or a grep you paste in the PR) checks `frontend/src` for it.
- [ ] The rider page can still ingest without the cookie.
- [ ] The slate shows an unlock field on 401/503 and paints events after a good unlock. `npm run check` and `pytest` pass.

## How to test

```bash
DISPATCH_PASSCODE=test-desk pytest backend/tests/test_dispatch_auth.py -q
# with API and frontend up:
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/events
curl -s -X POST http://127.0.0.1:8000/api/dispatch/unlock \
  -H 'Content-Type: application/json' -d '{"passcode":"test-desk"}' -c /tmp/rasta-cookie
curl -s -b /tmp/rasta-cookie http://127.0.0.1:8000/api/events
```

Open the desk in a browser, unlock once, refresh, and confirm the list still loads from the cookie. Confirm the rider chit in the same window never asked for the passcode.

<!-- rasta-voice-production-2026-11-12 -->

### Production: CSRF, lockout, and actor identity

- [ ] Unlock is rate-limited: after 5 wrong attempts from one address in 10 minutes, return 429 and do not compare further in a tight loop. A test covers the fifth failure.
- [ ] CSRF for desk POSTs is implemented here if issue 27 has not already, or is wired to 27's token. A passcode cookie alone must not be enough to ack or wipe.
- [ ] Support a synthetic dispatcher actor (`d_` token) on the cookie after unlock, for issue 25's audit. Do not use personal names or emails as the default actor.
- [ ] Document passcode rotation in `docs/DEPLOY.md` (change the secret, restart, existing cookies fail closed and must unlock again).
- [ ] Still no passcode in frontend source, logs, health, or ready payloads.
