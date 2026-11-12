# 23 — Docs pack

- **Labels:** `docs`, `day:3`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026), after issues 19–22 have merged so the docs describe the running app, not the plan.
- **Depends on:** issues 19, 20, 21, and 22. If one of those slips, write only what is actually on `main` and say what is still open. Do not document a feature as shipped because the issue exists.

## Description

Three short, truthful documents under `docs/`, linked from the README. Judges skim these. They have to match the merged code.

`docs/ARCHITECTURE.md`:

- A mermaid diagram of the real pipeline as it works on `main` the day you write it: rider chit, ingest/simulate routes, Prisma, extractor, store, slate, Timbre reply, and any live websocket or batch path that has actually merged.
- Solid arrows for paths you can exercise. Do not copy the README's dashed "issue plan" arrows for work that is still open. If issue 07 is not merged, the diagram has no working stream path.
- One short paragraph per box: which process, which env vars, which issue landed it.
- Point at `shared/rider_event.schema.json` as the frozen event contract, and at the ingest envelope (`id`, `created_at`, `stt`, `extractor_source` if present) as the store record.

`docs/SECURITY.md`:

- Key handling: `GNANI_API_KEY`, LLM keys, and `DISPATCH_PASSCODE` live in the environment or host secrets, never in git, images, client JS, logs, or the demo video.
- Credit caps and rate limits: describe issue 13 as it actually behaves (per-IP, global budget, 429/503).
- Dispatcher passcode: cookie or header, timing-safe compare, rider routes stay public (issue 20).
- Data policy: synthetic speech and synthetic order tokens only; consented field clips from issue 17 stay out of the repo; no real phone numbers, customer names, or government IDs.
- How to report a problem: open a GitHub issue on this repository, and never paste a secret into the issue.

`docs/CONTRIBUTING.md`:

- Trees and the one-owner-per-tree rule from `docs/PLAN.md` (Member A: `benchmark/` and benchmark docs; Member B: `backend/rasta/` except the frozen schema, `frontend/`, `Dockerfile`). Frozen files: `gnani_client/`, the shared schema, `schema.py`, `frontend/src/types.ts`. Do not restyle the other person's screen.
- Branch and PR: one issue per PR, name the issue, wait for CI (`ruff`, `pytest`, `npm run check`) to go green, no secrets in the branch.
- Commit messages: short imperative subject, optional body. The author is the person who did the work. No one-line dumps of the diff.
- Tests may use `httpx.MockTransport` inside test files. App code has no mock mode.

Link all three from the README in a short "Docs" line. Do not rewrite the product README's architecture section; a pointer is enough.

## Files to touch

- `docs/ARCHITECTURE.md` (new)
- `docs/SECURITY.md` (new)
- `docs/CONTRIBUTING.md` (new)
- `README.md` (links only)

## Do not touch

App and benchmark code, `gnani_client/`, issue files other than typo fixes you notice, the frozen schema.

## Input / output contract

Each doc is prose plus, for architecture, one mermaid `flowchart` that a reviewer can compare to `backend/rasta/` and `frontend/src/`. If a screenshot would help, skip it; mermaid is enough. No API keys, no passcodes, no real personal data.

## Acceptance criteria

- [ ] All three files exist and are linked from the README.
- [ ] The mermaid diagram matches merged behaviour on that commit, not the wish list. Open issues are named as open or omitted.
- [ ] `docs/SECURITY.md` covers keys, credit caps, passcode, synthetic-data policy, and a reporting path.
- [ ] `docs/CONTRIBUTING.md` covers branch, PR, commits, CI, and the one-owner-per-tree rule.
- [ ] Nothing in the three files contradicts `docs/PLAN.md` or claims a mock mode exists.

## How to test

Read the three files against `git ls-tree -r HEAD` and a walk of the running app (`/api/health`, `/api/ready`, a sample ingest if a key is present). Confirm the README links resolve.
