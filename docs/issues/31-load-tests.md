# 31 — Load tests and latency budgets

- **Labels:** `day:3`, `test`, `area:benchmark`
- **Owner:** Member A: Himanshu (@himanshu748), benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026), after health/ready and the passcode exist so the script can hit cheap routes hard, and speech routes only under a tight cap. Closes PERF-02, TEST-06, CON-03 (for test traffic).
- **Depends on:** issues 13 and 22. Prefer also 20 and 29 so unlock and the breaker are testable. Free tool only: k6 (preferred) or Locust. Do not use a paid load service.

## Description

Write a k6 script, `loadtest/k6.js` (or `benchmark/load/k6.js`), that can run against a base URL.

Scenarios:

1. **Ops**, always: `GET /api/health` and `GET /api/ready` at 20 virtual users for 30 s. No Gnani calls.
2. **Desk**, when `DISPATCH_PASSCODE` is set: unlock once per VU, then `GET /api/events` at 10 VUs for 30 s.
3. **Speech**, opt-in with `--env SPEECH=1` and only against localhost or a clearly named staging URL, never the public contest URL unless you have just rotated a budget and you cap it: at most 2 virtual users, at most 4 total `/api/ingest/sample` calls in the whole run. Honour issue 13's budget; stop on 429. This scenario is off in CI.

Latency budgets, documented in `docs/SLO.md` (create it; issue 34 can link it):

- `/api/health`: p95 under 100 ms local, 300 ms on the public host.
- `/api/events` (authed): p95 under 300 ms local, 800 ms on the public host.
- `/api/ingest/sample` (when run): p95 under 8 s, measured, not invented. Fail the script if a speech request has no `request_id` on success.

The script prints p50/p95, error rate, and the number of speech calls. It exits non-zero if ops or desk budgets fail, or if the error rate on those scenarios exceeds 1%. It never prints secrets.

CI (issue 33 can hook it): a job or a step that starts the API with a dummy key *and* tests that use the app's real health routes only — do not add a mock mode. For ops/desk in CI, the API can be up without a live Gnani key; health and ready still work. Do not call speech in CI.

## Files to touch

- `loadtest/k6.js` (new) and a short `loadtest/README.md`
- `docs/SLO.md` (new)
- `.github/workflows/ci.yml` only if issue 33 has not already reserved a step; otherwise describe the command and let 33 hook it
- `docs/PRODUCTION_READINESS.md` is already written; do not rewrite the tables

## Do not touch

App code, `gnani_client/`, frontend source. Do not point the default script at the public Space with `SPEECH=1`.

## Input / output contract

```bash
k6 run loadtest/k6.js -e BASE_URL=http://127.0.0.1:8000 -e DISPATCH_PASSCODE=test-desk
```

Exit 0 if ops and desk budgets hold. Speech is skipped unless `SPEECH=1`.

## Acceptance criteria

- [ ] Script and `docs/SLO.md` exist and name the budgets above.
- [ ] A local run against the API (no speech) is pasted in the PR (p95 numbers, VU count).
- [ ] Speech remains opt-in and capped at 4 sample calls.
- [ ] The script exits non-zero on a forced failure (for example a wrong `BASE_URL`).
- [ ] No passcode or API key in the script output or in `docs/SLO.md`.

## How to test

Install k6 (free). Start the API. Run the command above. Then `k6 run loadtest/k6.js -e BASE_URL=http://127.0.0.1:9` and confirm a non-zero exit.
