# 19 — SQLite event store

- **Labels:** `area:app`, `day:2`, `api`
- **Owner:** Member B: app & realtime
- **Target day:** Day 2 (13–14 Nov 2026). Land this early on Day 2, once issue 04 is merged, so a refresh or a process bounce does not wipe the desk during the rest of the day's demos.
- **Depends on:** issue 04. Keep the same store interface (`append`, `list_since`, cap 200, stamped `id` and `created_at`) so issue 10 and later routes do not change their JSON.

## Description

Issue 04's in-memory list is correct for Day 1 and wrong for a public demo: one uvicorn restart, or a free-host recycle, empties the slate. Replace the list with stdlib `sqlite3` behind the same interface. Do not add Postgres, Redis, or a paid database. Do not add an ORM.

`backend/rasta/store.py` (the file issue 04 added; this issue rewrites its insides):

- The app opens a file database. Path comes from `RASTA_DB_PATH`. Default to `data/rasta-events.sqlite` relative to the process working directory, and create parent folders if needed.
- Schema: one table for the stamped ingest record. Store the payload as JSON text plus `id` and `created_at` columns you can filter on. Keep the cap at 200: on append, delete the oldest rows when the count exceeds 200.
- `append(result: dict) -> dict` and `list_since(since: str | None) -> list[dict]` keep the exact behaviour and JSON shape from issue 04, including any extra envelope fields (for example `extractor_source` from the issue 02 hardening, or `sample_text`). Do not drop unknown keys.
- One `threading.Lock` around write + trim remains fine for a single worker. Comment it the same way: one demo process.
- WAL mode is optional; if you enable it, say so in a comment. Do not require a second process.

In-memory stays a constructor argument for tests only, for example `EventStore(path=":memory:")` or `EventStore(memory=True)`. There is no `RASTA_STORE=memory` flag, no mock mode, and no request header that switches the store. The running app always uses the file path.

Free-host disk is ephemeral. A Space rebuild or a Render spin-down can delete the file even though a local restart on the same disk does not. Document that honestly in `docs/DEPLOY.md` (create the file if issue 13 has not yet, or add a short "Storage" section if it has). Do not claim the desk is durable. Do not switch the production app back to an in-memory list to "fix" a wiped Space.

Wire the app to construct one store at import or in the lifespan, and keep using it from ingest and `GET /api/events`. One uvicorn worker, same as issue 04. Do not add auth in this issue (that is issue 20).

## Files to touch

- `backend/rasta/store.py` (replace the list, keep the public methods)
- `backend/rasta/main.py` or `routes_events.py` only if the constructor needs a path
- `backend/tests/test_store.py` (extend; keep the cap and `since` cases)
- `.env.example` (add `RASTA_DB_PATH=` with a comment)
- `.gitignore` if the default data file would otherwise be committed
- `docs/DEPLOY.md` (storage paragraph; create only if missing)

## Do not touch

`frontend/`, `benchmark/`, `gnani_client/`, `schema.py`, `extract.py`. Do not change the `/api/events` URL or the event JSON keys from issue 04.

## Input / output contract

Same as issue 04. `POST /api/ingest` and `POST /api/ingest/sample` still return the stamped record. `GET /api/events` and `GET /api/events?since=` still return `{"events": [...]}` in created order.

Restart contract: two appends, process exit, new process pointed at the same `RASTA_DB_PATH`, `list_since(None)` returns both rows with the same ids.

## Acceptance criteria

- [ ] The production constructor reads `RASTA_DB_PATH` and writes a real sqlite file. No app flag selects an in-memory store.
- [ ] Tests may pass `":memory:"` (or an equivalent constructor arg) and still cover cap 200, `since`, and append shape. Existing ingest tests still pass.
- [ ] A test writes to a temp file, opens a second `EventStore` on that path, and sees the same events. That is the restart test.
- [ ] Extra keys on the ingest dict survive a round trip through sqlite.
- [ ] `docs/DEPLOY.md` states that free-host disk is ephemeral and a rebuild can wipe the desk.
- [ ] `pytest` and `ruff check backend` pass. No network. The default data file is not committed.

## How to test

```bash
pytest backend/tests/test_store.py backend/tests/test_ingest.py -q
RASTA_DB_PATH=/tmp/rasta-events.sqlite uvicorn rasta.main:app --port 8000
# ingest once (needs GNANI_API_KEY for /api/ingest/sample), restart uvicorn, then:
curl -s http://127.0.0.1:8000/api/events | python -m json.tool
```
