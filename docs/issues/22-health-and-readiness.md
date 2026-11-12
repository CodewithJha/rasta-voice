# 22 — Health and readiness

- **Labels:** `area:app`, `day:3`, `observability`, `deploy`
- **Owner:** Member B: app & realtime
- **Target day:** Day 3 (14–15 Nov 2026), once issue 13's limiter and issue 19's database exist to report on.
- **Depends on:** issues 13 and 19. Read the counter and store those issues actually shipped; do not invent a second budget.

## Description

`GET /api/health` stays a cheap liveness probe: the process is up. The skeleton already returns `ok`, `gnani_key_set`, and `llm_provider`. Keep that shape and do not put disk, budget, or passcode state on it, so a tight restart loop cannot fail because sqlite is mid-migrate or the budget is spent.

Add `GET /api/ready` as readiness:

- `gnani_key_set`: boolean, same check as health.
- `db_writable`: boolean. Open the issue 19 store path and perform a no-op write (for example a `BEGIN IMMEDIATE` / rollback, or a ping table). If the file cannot be created or written, this is false.
- `rate_limit`: a small object from issue 13's limiter (remaining per-IP quota, or "not configured" if 13 used different names — adapt, don't fork).
- `demo_credits_remaining`: integer, or an object with `remaining` and `window`, taken from issue 13's global Gnani-call budget. When the budget is exhausted, readiness can still be 200 if you want the host to keep the process, but the payload must show `0` remaining and a clear `demo_credits_exhausted: true`. Pick one behaviour, document it in `docs/DEPLOY.md`, and do not hide exhaustion behind `ok: true` with no other fields.
- HTTP 200 when the process can serve the demo (key may be missing: report it, still 200, because a misconfigured Space should stay up and answer 503 on speech routes). HTTP 503 only when the process should be taken out of rotation, for example the database is not writable. Do not 503 solely because the Gnani key is missing; health already tells you that, and a 503 loop on a missing secret makes the logs worse.

Do not include `DISPATCH_PASSCODE`, `GNANI_API_KEY`, or any raw secret in either payload.

Wire the free host's health check to `/api/ready` in `docs/DEPLOY.md` (Spaces or Render, whichever issue 13 chose). If the host only accepts `/api/health`, say so and keep health as liveness; still ship `/api/ready` for operators and for issue 24.

## Files to touch

- `backend/rasta/main.py` or a small `routes_health.py` (new ready route; leave health in place)
- `backend/tests/test_health.py` (new, or extend an existing health test)
- `docs/DEPLOY.md` (health-check path and the credit-exhausted behaviour)

## Do not touch

`frontend/`, `benchmark/`, `gnani_client/`, `schema.py`. Do not add a paid uptime vendor.

## Input / output contract

`GET /api/health`:

```json
{"ok": true, "gnani_key_set": true, "llm_provider": "rules"}
```

`GET /api/ready` (shape may add keys, but must include these):

```json
{
  "ok": true,
  "gnani_key_set": true,
  "db_writable": true,
  "rate_limit": {"ok": true},
  "demo_credits_remaining": 40,
  "demo_credits_exhausted": false
}
```

200 when the process should stay in rotation. 503 with `ok: false` and `db_writable: false` when the store cannot be written. Exact limiter keys may follow issue 13; document them in the PR if they differ.

## Acceptance criteria

- [ ] `/api/health` is unchanged in meaning and still wins over any static mount from issue 13.
- [ ] `/api/ready` reports key set, db writable, rate-limit state, and remaining demo credits from issue 13's counter.
- [ ] A test points the store at a non-writable path (or patches the check) and gets 503 with `db_writable: false`.
- [ ] A test with a writable temp db and a stubbed limiter returns 200 and the remaining budget.
- [ ] Payloads never contain secrets. `docs/DEPLOY.md` points the host health check at the path you chose and describes credit exhaustion.
- [ ] `pytest` and `ruff check backend` pass. No network.

## How to test

```bash
pytest backend/tests/test_health.py -q
curl -s http://127.0.0.1:8000/api/health | python -m json.tool
curl -s -o /tmp/ready.json -w "%{http_code}\n" http://127.0.0.1:8000/api/ready
python -m json.tool /tmp/ready.json
```

<!-- rasta-voice-production-2026-11-12 -->

### Production: breaker, schema, and errors

- [ ] `/api/ready` also reports `schema_version` (issue 19), circuit-breaker state (issue 29), and `events_in_store`. Missing pieces are `"not_deployed"` rather than a lie.
- [ ] Ready stays 503 only when the process should leave rotation (database not writable, or a required migrator failed). An open breaker or a spent credit budget is 200 with flags set, as already specified, so the host does not flap.
- [ ] `/api/health` stays cheap and does not touch SQLite or Gnani.
- [ ] Error counts since boot may appear here or only on `/api/admin/usage` (issue 25); do not fork two counters.
