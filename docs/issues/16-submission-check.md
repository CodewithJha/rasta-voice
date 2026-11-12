# 16 — Submission checklist

- **Labels:** `area:benchmark`, `day:3`, `contest`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026), after the post is up and before **15 Nov 2026, 18:00 IST**.
- **Depends on:** issues 12, 13, and 15. You are checking their output, not rebuilding it. If one of them is late, the checklist says "not done" in that row and you do not tick it. Don't tick from memory.

## Description

Write `docs/SUBMISSION.md` by walking the product as a judge would, and record what you found. This is the last pass. It is short on purpose.

Run, from a clean checkout, the README setup (venv, `pip install -r requirements-dev.txt`, `pytest`, `npm run check`). Paste the pytest summary line (the `N passed` line), not the whole log.

Then confirm:

| Check | How | Done when |
| --- | --- | --- |
| Live hello path | `POST /api/ingest/sample` with `GNANI_API_KEY` set | Intent is `customer_unreachable`, order `18`, with a real Prisma `request_id` |
| Gnani is actually used | README architecture plus one live `request_id` from a Prisma response and one Timbre clip duration | The id is written in the doc. The key is not |
| No mock paths | `rg -n -i "mock\|GNANI_MOCK\|canned" --glob '!**/tests/**' --glob '!docs/issues/**' .` | No hits outside tests (tests may use `httpx.MockTransport`) |
| Missing key is loud | Start the API with `GNANI_API_KEY` unset, call `/api/ingest/sample` | 503 with the missing-key message |
| Benchmark section | README between the markers | Table, SVG, the word synthetic, run date and grid size from the live run |
| No real personal data | `rg -n "[0-9]{8,}" benchmark/data docs backend frontend shared` | No hits, or every hit explained as a non-personal token |
| Demo script | `docs/demo-script.md` | Total read-through ≤ 60 s |
| Post | `docs/social-post.md` | Both links present |
| Deploy | `docs/DEPLOY.md` | Public URL returns `/api/health` with `"ok": true` |
| Deadline | clock | Submitted before 15 Nov 2026, 18:00 IST |

Fix only what this pass finds, and only if the fix is inside your trees (`benchmark/`, the benchmark README section, this doc). If a check fails in Member B's tree, write the failure in the doc and point them at the file. Don't quietly rewrite the frontend on the last afternoon.

## Files to touch

- `docs/SUBMISSION.md` (new)
- Bugfixes in `benchmark/` or the README benchmark section, only if a check fails there

## Do not touch

`frontend/src/`, `backend/rasta/` except to file a note. `gnani_client/` unless the live call fails on a bug you can show with a failing test.

## Input / output contract

`docs/SUBMISSION.md` contains the table above filled with `yes` or `no`, a one-line evidence note per row, the pytest summary, the deploy URL, the two post URLs, and the live `request_id` or the words `credits not in yet`.

## Acceptance criteria

- [ ] Every row has yes or no, plus evidence.
- [ ] The personal-data search was run and the output (or "no matches") is in the doc.
- [ ] You did not paste `GNANI_API_KEY`, `GROQ_API_KEY`, or `GEMINI_API_KEY`.
- [ ] A `no` row names the owner who has to close it.
- [ ] The file is committed before the contest deadline, even if a row is still `no`. An empty checklist is worse than an honest one.

## How to test

Follow the README from a new venv. Run the `rg` command in the table. `curl` the deployed `/api/health`. Read the demo script with a timer. Open both post URLs and confirm they resolve.
