# 26 — API contract: errors, idempotency, pagination, OpenAPI

- **Labels:** `area:app`, `day:3`, `api`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 3 (14–15 Nov 2026). Can start as soon as 04/19 routes exist; land alongside 21 so every error carries a request id. Closes API-01, API-02, API-03, API-04, API-05, SEC-05, REL-04, REL-07, REL-08, TEST-04, DOC-04.
- **Depends on:** issues 19 and 21. Does not wait on 25, but the error envelope and `If-Match` must not fight 25's 409 bodies.

## Description

Give the API one predictable contract so the UI, the smoke script, and operators can trust it.

Error envelope, every 4xx/5xx including 401/403/409/429/502/503:

```json
{"error": {"code": "missing_api_key", "message": "GNANI_API_KEY is not set.", "request_id": "..."}}
```

- `code` is a stable snake_case token (`missing_api_key`, `upstream_error`, `upstream_rate_limited`, `upstream_out_of_credit`, `validation_error`, `not_found`, `unauthorized`, `forbidden`, `version_conflict`, `illegal_transition`, `rate_limited`, `budget_exhausted`, `payload_too_large`, `unsupported_media_type`).
- `message` is safe for a UI. Do not forward raw upstream bodies or secrets (SEC-05).
- `request_id` is the value of `X-Request-ID` from issue 21.
- Map Gnani 429 to HTTP 429 with `upstream_rate_limited`, 402 to 503 with `upstream_out_of_credit`, other Gnani failures to 502 with `upstream_error` and `upstream_status` as an optional extra field on `error`, not a second shape.

Keep the current `/api/...` paths. Treat them as v1. Add `/api/v1/...` as aliases that call the same handlers so a later breaking change can live under v2. Do not drop the unversioned paths in this contest window.

Idempotency: credit-spending POST routes (`/api/ingest`, `/api/ingest/sample`, `/api/simulate`, `/api/reply/{id}`, and the stream start if it is a POST) accept `Idempotency-Key` (a UUID or a `^[\w.-]{8,128}$` token). Store the key, route, status, and response body for 10 minutes in SQLite (issue 19). A replay with the same key and the same body returns the stored response and does not call Gnani again. A same key with a different body is 409 `idempotency_conflict`. Keys are hashed at rest. The rider and dispatch frontends must send a key on those clicks (coordinate with 09, 10, and 30 if those PRs are in flight; otherwise set the header in this PR in `rider.ts` / `dispatch.ts` only as much as needed).

Pagination: `GET /api/events` supports `limit` (default 50, max 200) and `since` as today, plus `page_token` (the last `id`+`created_at`) for a stable page. The response is `{"events": [...], "next_page_token": null}`. Issue 10's poll can keep using `since`.

OpenAPI: tag routes (rider, dispatch, admin, ops). Write a short `docs/API.md` that points at `/openapi.json` on a local server and at the error envelope, idempotency, and pagination rules. In production (issue 27) `/docs` may be disabled; the markdown stays.

## Files to touch

- `backend/rasta/errors.py` (new envelope and exception handlers)
- `backend/rasta/main.py` (handlers, aliases)
- `backend/rasta/idempotency.py` (new)
- `backend/rasta/routes_events.py` (pagination)
- `backend/tests/test_api_contract.py` (new)
- `frontend/src/rider.ts` and `dispatch.ts` only to send `Idempotency-Key` and to read `error.message`
- `docs/API.md` (new)
- `backend/tests/test_ingest.py` (update assertions that read `detail` as a string)

## Do not touch

`gnani_client/`, `benchmark/`, the frozen `RiderEvent` schema, issue 25's transition rules.

## Input / output contract

See the error JSON above. A second `POST /api/ingest/sample` with the same `Idempotency-Key` returns the same `id` and `stt.request_id` and produces no additional outbound Gnani HTTP call (assert on a swapped transport).

## Acceptance criteria

- [ ] Every existing error path (400, 413, 401 after 20, 502, 503, and 429 once 13 exists) uses the envelope and includes `request_id`. Tests cover 400, 503, and 502 at minimum.
- [ ] Gnani 429 and 402 are mapped as above, not as a generic 502.
- [ ] Idempotency replay does not call Gnani the second time. Conflict on a reused key with a different body is 409.
- [ ] `/api/v1/health` and `/api/health` both work. `/api/events` pagination returns `next_page_token` correctly.
- [ ] `docs/API.md` describes the envelope, headers, and aliases. `pytest` and `ruff` pass. Frontend still compiles.

## How to test

```bash
pytest backend/tests/test_api_contract.py backend/tests/test_ingest.py -q
curl -sD - http://127.0.0.1:8000/api/ingest/sample -o /tmp/err.json   # no key → 503 envelope
```
