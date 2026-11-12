# 28 — Privacy, redaction, retention, and deletion

- **Labels:** `area:app`, `day:3`, `security`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 3 (14–15 Nov 2026), after the SQLite store exists. Closes PRIV-01, PRIV-02, PRIV-03, PRIV-04, PRIV-05, PRIV-06, DATA-04, PROD-05 (with 25).
- **Depends on:** issue 19. Passcode protection from 20 applies to delete and export routes. Audit rows from 25 should record deletes if 25 has landed; if not, write a local audit or a log line in the issue 21 JSON format and let 25 attach the table later.

## Description

Treat stored speech text as sensitive even though the contest is synthetic. A phone number that slipped into a transcript should not sit on the slate, and an operator must be able to wipe the desk.

Redaction: before `store.append`, and again before any list/detail response, run a redactor over `transcript`, `sample_text`, and `event.transcript`:

- Digit runs of 8 or more, and obvious `+91` / spaced Indian mobile shapes, become `[redacted]`.
- The existing rule that an 8-digit run is never an `order_id` stays.
- Do not redact short order tokens (`18`, `order eighteen`).
- Tests include a line with `9876543210` and a line with `order 18`.

Retention:

- `RASTA_EVENT_TTL_HOURS` (default 24) is the wall-clock lifetime of an event row. A sweeper (on a short interval in the lifespan, and once on boot) deletes expired rows and their audit rows, and logs the count without ids of deleted riders if you can avoid it — event ids are fine.
- The cap of 200 remains a safety valve, but evicting a `new` or `escalated` `accident_sos` is not silent: write an audit (or log) event `evicted` and, if 25 exists, prefer evicting `resolved` rows first.

Deletion:

- `DELETE /api/events/{id}` is passcode-protected, CSRF-protected once 27 lands, and removes the row and its audit detail (or retains a tombstone audit row without the transcript). 404 if missing. 204 on success.
- `DELETE /api/admin/events?confirm=wipe` (or `POST /api/admin/wipe` with `{"confirm":"wipe"}`) clears the desk store. Usage counters may stay. This is the "wipe this desk" path.

Audio: a test, or a small invariant in the PR, greps the backend for write paths under `benchmark/data` or `/tmp` and asserts that simulate, reply, and ingest do not write wav files. Debug dumps, if any, are off by default and refused when `RASTA_ENV=prod`.

Classification: a short paragraph in `docs/SECURITY.md` or the PR, reused by issue 34: only synthetic speech, no real customer calls, field clips from issue 17 stay off this host.

## Files to touch

- `backend/rasta/redact.py` (new)
- `backend/rasta/store.py` (TTL sweeper, delete, eviction order)
- `backend/rasta/routes_events.py` (delete, wipe)
- `backend/rasta/pipeline.py` (call the redactor before append)
- `backend/tests/test_privacy.py` (new)
- `.env.example` (`RASTA_EVENT_TTL_HOURS=24`)
- `docs/SECURITY.md` only if issue 23 already created it

## Do not touch

`frontend/src/rider.ts` (the chit already shows whatever the API returns; redacted text should just appear). You may add a "Wipe desk" control on the slate in `dispatch.ts` behind a confirm step. `gnani_client/`, `benchmark/`, frozen schema.

## Input / output contract

Ingest of a clip whose transcript contains `9876543210` stores and returns `transcript` with `[redacted]` and `order_id` still a short token if one was spoken.

`DELETE /api/events/{id}` → 204, then `GET /api/events` does not include that id. `GET` after TTL expiry (test with a negative or zero TTL / patched clock) is empty for that row.

## Acceptance criteria

- [ ] Redaction tests as above; order 18 survives; 10-digit numbers do not appear in store list or audit transcripts.
- [ ] TTL sweeper is tested with a patched timestamp or a 0-hour TTL.
- [ ] Delete and wipe are passcode-protected, and wipe requires an explicit confirm token.
- [ ] Eviction of a live SOS is logged. Cap 200 still holds for a pile of resolved rows.
- [ ] No audio file is written by ingest/simulate/reply in tests.
- [ ] `pytest` and `ruff` pass. No secrets in the new routes' error bodies.

## How to test

```bash
pytest backend/tests/test_privacy.py -q
```
