# 32 — Quality gates: types, coverage, Playwright, contract tests

- **Labels:** `day:3`, `test`
- **Owner:** Member A: Himanshu (@himanshu748), benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026). Can land in parallel with 33 (CI wiring). Closes TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, FE-06 (CI hook), CICD-01 (with 33).
- **Depends on:** issues 09, 10, and 24. Playwright covers the screens those issues built. If 20 or 25 have merged, include unlock and ack; if not, skip those cases with a clear comment.

## Description

Raise the automated bar so a change cannot land untyped, untested, or visually broken.

Python types: add `mypy` (or `pyright`) in `requirements-dev.txt` and a `mypy.ini` / pyproject section for `backend/rasta`, `gnani_client`, and `benchmark`. Third-party libs may need ignore missing imports. CI fails on new errors. Do not weaken the app to please the checker.

Coverage: `pytest --cov=backend/rasta --cov=gnani_client --cov=benchmark --cov-report=term-missing` with `--cov-fail-under=80` (adjust to 75 only if you justify it in the PR against today's baseline, not to sneak past untested branches). Omit test packages.

Frontend unit tests: add `vitest` (free) and at least tests for the i18n catalogue (if 30 landed) or for a pure helper extracted from `rider.ts` / the envelope type guard. `npm run test` must be non-interactive.

Playwright: add `@playwright/test` as a dev dependency. A smoke spec loads `/`, checks the rider and slate landmarks, runs **Speak a sample line** only when `GNANI_API_KEY` is set (otherwise asserts the 503 / missing-key UI), checks 360 px overflow, and keyboard-focuses the primary button. Against a live key, assert the chit shows `customer_unreachable` and that the slate updates. Never screenshot a secret. The job is `opt-in` for the live path (`playwright.config.ts` skips it in CI without a key) and always runs the key-less UI path in CI, which may start the API with no key and the built frontend.

Contract tests: extend `backend/tests/test_schema.py` (or a new `test_envelope.py`) so the ingest envelope (`id`, `created_at`, `stt`, `event`, and optional `extractor_source`, `state`, `version`) is schema-checked with Pydantic models that *allow* extra envelope keys but still reject a broken `event`. Export or compare a snapshot of `/openapi.json` in dev if issue 26 landed.

Lighthouse: if 30 added a budget file, add a documented command. Making it a required CI gate is optional in this window (it is slow); a `workflow_dispatch` or a weekly hint in issue 33 is enough. Do not fail every PR on flaky Lighthouse if you cannot pin the runner.

Issue 24's `scripts/smoke.py` stays the API-level live smoke. This issue does not replace it.

## Files to touch

- `requirements-dev.txt`, `mypy.ini` or `pyproject` tool config, `pytest.ini`
- `frontend/package.json`, `frontend/vitest.config.ts` (new), `frontend/src/**/*.test.ts` (new)
- `frontend/playwright.config.ts`, `frontend/tests/e2e/*.ts` (new)
- `backend/tests/test_schema.py` or `backend/tests/test_envelope.py`
- `.github/workflows/ci.yml` (or leave hooks clearly listed for issue 33)

## Do not touch

App behaviour, `gnani_client` production code except type hints, frozen schema meaning. Do not add a mock flag to pass e2e.

## Input / output contract

```bash
mypy backend/rasta gnani_client benchmark
pytest --cov-fail-under=80
cd frontend && npm run test && npx playwright test
```

CI without secrets: mypy, pytest+coverage, vitest, Playwright key-less spec, all green.

## Acceptance criteria

- [ ] `mypy` is clean on the three packages, or the remaining ignores are listed and justified in the PR.
- [ ] Coverage floor is enforced in CI and is at least 75%, with 80% the target.
- [ ] At least three vitest cases pass.
- [ ] Playwright key-less spec passes in CI. The live spec is skipped without a key and passes locally when a key is present (paste a note, not the key).
- [ ] Envelope contract tests fail if `event` loses `intent` or gains a forbidden property.
- [ ] `scripts/smoke.py` still runs as before.

## How to test

The commands above, plus a deliberate schema break to see the contract test fail, then revert it.
