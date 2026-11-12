# 04 — In-memory dispatch event store

- **Labels:** `area:app`, `day:1`, `api`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 1 (12–13 Nov 2026)
- **Depends on:** skeleton merged. Parallel with issue 02. Do not edit `extract.py` in this PR if 02 is also in flight; this issue only stores whatever `ingest` already returns.

## Description

The slate needs a list, not a single response that disappears on refresh. Keep the events in process memory. There is no database. A restart clears the desk, and that is fine for the demo.

Add `backend/rasta/store.py`:

- A list guarded by one `threading.Lock`. Comment it: `# ponytail: one global lock, fine for one demo process`.
- `append(result: dict) -> dict` stamps `id` (uuid4 string) and `created_at` (UTC ISO 8601) onto a copy. It stores the ingest payload (`transcript`, `stt`, `event`) plus those two fields.
- Cap 200. Drop the oldest.
- `list_since(since: str | None) -> list[dict]` returns events with `created_at` strictly after `since`, or every event when `since` is missing. Preserve order.

Wire it from the existing ingest helpers. Put the new route on its own router so later issues are not all editing the same function.

- `backend/rasta/routes_events.py` — `APIRouter`, `GET /api/events`.
- `backend/rasta/main.py` — one line, `app.include_router(events_router)`. Inside `_run`, after a successful `ingest`, call `store.append` and return the stamped record (so the chit and the desk share an id).

Do not add persistence, auth, or a second process. The desk is one uvicorn worker.

## Files to touch

- `backend/rasta/store.py` (new)
- `backend/rasta/routes_events.py` (new)
- `backend/rasta/main.py` (the include line and the `append` call only)
- `backend/tests/test_store.py` (new)

## Do not touch

`frontend/` (issue 10 paints this), `benchmark/`, `gnani_client/`, `extract.py`, `schema.py`.

## Input / output contract

`POST /api/ingest` and `POST /api/ingest/sample` return the same JSON as today, plus:

```json
{
  "id": "uuid",
  "created_at": "2026-11-13T10:00:00+00:00",
  "transcript": "...",
  "stt": {"model": "prisma-v3.0", "request_id": "01a1ceb8-be35-7a20-b209-af966a3bb25a", "detected_language_code": null, "processing_time": 0.21, "audio_seconds": 6.08},
  "event": {"intent": "customer_unreachable", "order_id": "18"}
}
```

`GET /api/events` returns `{"events": [ ...same objects... ]}`.

`GET /api/events?since=2026-11-13T10:00:00+00:00` returns only newer ones.

## Acceptance criteria

- [ ] Two ingests produce two stored events, oldest first. In tests, swap the Gnani HTTP transport the way `backend/tests/test_ingest.py` does; no fake path in app code.
- [ ] The 201st append drops the oldest. Test this by calling `append` directly, not via HTTP.
- [ ] `since` filters by `created_at`.
- [ ] Existing ingest tests still pass. Update them only if they assert the exact key set and now reject `id`.
- [ ] `pytest` and `ruff check backend` pass. No network.

## How to test

```bash
pytest backend/tests/test_ingest.py backend/tests/test_store.py -q
curl -s -X POST http://127.0.0.1:8000/api/ingest/sample >/dev/null   # real Timbre + Prisma, needs GNANI_API_KEY
curl -s http://127.0.0.1:8000/api/events | python -m json.tool
```

