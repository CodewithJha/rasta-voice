# HTTP API contract

This is the operator-facing contract for the local (or deployed) server. Generated docs live at `/docs` and `/openapi.json` on a development server. In production those routes may be disabled; this file stays the reference.

Unversioned `/api/...` paths are v1 for this contest window. The same handlers also answer under `/api/v1/...` (for example `/api/v1/health` and `/api/health`). Do not drop the unversioned paths yet.

Routes are tagged in OpenAPI as **rider**, **dispatch**, **admin**, and **ops**.

## Errors

Every API 4xx/5xx, including 401, 403, 409, 429, 502 and 503, uses this envelope:

```json
{"error": {"code": "missing_api_key", "message": "GNANI_API_KEY is not set.", "request_id": "..."}}
```

- `code` is a stable snake_case token (`missing_api_key`, `upstream_error`, `upstream_rate_limited`, `upstream_out_of_credit`, `validation_error`, `not_found`, `unauthorized`, `forbidden`, `version_conflict`, `illegal_transition`, `idempotency_conflict`, `rate_limited`, `budget_exhausted`, `payload_too_large`, `unsupported_media_type`, and a few existing operational tokens such as `timeout` and `shutting_down`).
- `message` is safe for a UI. Upstream bodies and secrets are never forwarded.
- `request_id` matches the `X-Request-ID` response header.
- Optional extras stay inside `error`: `upstream_status` on Gnani failures, and `version` / `state` on dispatcher `version_conflict` / `illegal_transition` (issue 25).

Gnani mapping: HTTP 429 becomes 429 `upstream_rate_limited`; 402 becomes 503 `upstream_out_of_credit`; any other Gnani failure becomes 502 `upstream_error` with optional `upstream_status`.

`GET /api/ready` is the issue 22 probe. A 503 there is still the structured readiness document (`ok`, `db_writable`, `schema_version`, …), not this envelope, so a host probe does not look like an API error.

## Idempotency

Credit-spending POSTs (`/api/ingest`, `/api/ingest/sample`, `/api/simulate`, `/api/reply/{id}`) accept an `Idempotency-Key` header: a UUID or a `^[\w.-]{8,128}$` token. The server stores hashes of the key, canonical route and request body, plus status for 10 minutes in the desk SQLite database. Full response bodies (including generated audio) stay only in a bounded 128-entry / 8 MiB process memory cache. A replay with the same key and body returns that response while it is available in memory and does not call Gnani again. After eviction or restart it returns 503 `idempotency_response_unavailable`; the retained key metadata prevents another paid execution during its lifetime. The same key with a different body is 409 `idempotency_conflict`. Keys are hashed at rest. A missing key is still accepted so older clients keep working; the rider UI sends a key on those clicks.

A concurrent identical request returns 409 `idempotency_in_progress` while the
original runs; reuse the same key after it completes to obtain the stored
result. A concurrent different body/query is an idempotency conflict. This
claim is process-local under the documented one-worker topology. Completed key
metadata persists for ten minutes; a process crash before recording an
upstream result cannot provide a cross-process exactly-once guarantee.
Cancellation or an exception before response capture records a conservative
503 `idempotency_outcome_unknown`, so retrying that key cannot launch uncertain
paid work again. This is not permission to retry with a new key.

Keyed request bodies are capped at 2 MB plus 64 KiB multipart framing before
buffering, including chunked or understated lengths. Replays, conflicts and
validation denials retain the response security policy. Error bodies receive
the current HTTP `X-Request-ID`; the cached Gnani/event identifiers in a
successful response remain those of the original work. A response referencing
a deleted or expired event is unavailable even if its memory TTL has not
elapsed. SQLite replay rows contain no transcript or base64 audio.


## Pagination

`GET /api/events` returns `{"events": [...], "next_page_token": null}`. Query parameters:

- `since` — existing created_at cursor (issue 10 / 19)
- `updated_since` — existing change cursor (issue 25)
- `limit` — default 50, maximum 200
- `page_token` — opaque token for the last `id` and `created_at` of the previous page

When more rows remain, `next_page_token` is set. The desk poll can keep using `updated_since` and should pass `limit=200` (the store cap) so a default page of 50 cannot hide live rows.
