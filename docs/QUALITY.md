# Quality gates

Checked on 15 November 2026 IST against merged main `5facb55` and the
independently checked pending PR 99 head `cd71328`. Python, frontend, contract,
keyless browser, load, secret, dependency, SAST and production-container checks
all pass on that head. The combined local candidate with PRs 95/96/97/99 has
1,920 passing Python tests, one live-provider test skip, one strict accuracy
expected failure and 91.01% production coverage. It is not merged or deployed.
The strict public live sample still fails order-number acceptance; the
[deployment record](DEPLOY.md) gives the actual outcome and limitations.

## Python

Use Python 3.12 and install `requirements-ci.lock` into a fresh virtual env.
From the repository root:

```bash
mypy backend/rasta gnani_client benchmark
ruff check gnani_client backend benchmark
pytest
python scripts/check_frontend_types.py
```

Mypy targets the documented Python 3.11 source minimum while CI runs on 3.12.
It checks the production packages above, including bodies of untyped functions.
The dated integration evidence records the current source count.
Test/build directories are excluded; no production module is ignored and no
new type-ignore or missing-import suppression is added. Existing broad dict/Any
annotations are not a claim of strict end-to-end typing. The existing
create_task argument suppression in tasks.py predates this PR.

pytest.ini enables pytest-cov by default and .coveragerc names only the three
production package trees. Tests are omitted. The required line-coverage floor
is 80%; baseline was 90.84%, and the new envelope tests measure 90.86%. Coverage
is not reduced to make a gate pass. CI's full `python` job enforces the floor.
The focused `contract` job uses `--no-cov` because it intentionally runs only
schema/envelope tests; the full coverage job must also pass.

The test-only Pydantic envelope validates UUID/time, speech request ID and the
unchanged strict RiderEvent. Extra envelope metadata, including lifecycle keys,
is permitted; missing intent or an extra property inside event is rejected.
The actual upload/sample routes are exercised with test-confined HTTP transport
replacements. There is no application mock mode or fixture score path. A local
negative control temporarily allowed extra RiderEvent fields: the new guard
failed, then passed after the original schema file was restored.

## Frontend

From `frontend/`, with Node 22:

```bash
npm ci
npm run check
npm run check:tests
npm run test
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

`check` runs source type checking and four Node regressions. `check:tests` also
type-checks test/config code. Vitest runs 23 cases, including the i18n catalogue,
record/parser/cursor, CSRF, reply presentation, API errors and timeout behavior.
These are unit checks, not browser or audio-listening evidence. The optional
[frontend performance budgets](../frontend/lighthouse-budget.json) describe the separate
Lighthouse check; it is not a required PR gate.

## Real key-less browser path

The Playwright config builds the frontend and starts a fresh one-worker
FastAPI process serving those assets directly at http://127.0.0.1:8000.
Existing servers are never reused. The key-less default explicitly empties
GNANI_API_KEY in the server environment, even if a shell or ignored .env has a
key, and selects the rules extractor. A no-key HTTP 503 is the real route's
response, not browser interception. No route is fulfilled with fixture JSON.

At desktop 1280 px and mobile 360/400 px, tests check page identity, rider/slate
regions, keyboard access and Enter activation of the sample button, the missing
key UI, recovery of controls, an empty desk and horizontal overflow. Uncaught
page exceptions fail the test. The expected HTTP 503 is intentional. Tests do
not certify color contrast, every visual detail, audio listening or field
accuracy. Key-less screenshots are kept as a short-lived CI artifact; traces
and automatic live screenshots are disabled.

The browser-smoke job always runs without provider secrets. Eight keyless cases
exercise viewports, keyboard controls, language, CSP, the signed unlock
challenge and the real Ack/Resolve workflow. A synthetic per-run fixture gives
the desk a stored event; it does not fabricate speech. The single live browser
test skips without an explicit opt-in.
If Chromium cannot launch in a constrained local workspace, run these same
commands on a normal developer machine or use the CI browser-smoke result;
do not report the local launch error as an application regression.

## Opt-in live path

Only after checking the remaining provider credit budget, set the server key
privately in the environment and run:

```bash
RASTA_E2E_LIVE=1 npm run test:e2e -- --grep "noisy synthetic sample"
```

This starts a new local server with that key, performs one noisy synthetic
sample (Timbre plus Prisma, two speech calls), requires a non-empty request ID,
customer_unreachable for order 18, and the same event in a second browser window
and after refresh. Retries are zero. Never paste the key in the command itself
or upload traces. A failed upstream call remains a failure; it does not switch
to canned output. The live path is not claimed as passed by a key-less CI run.

Issue 24's [API smoke script](../scripts/smoke.py) is merged and remains
separate. Actual public health, passcode/CSRF/error/header checks passed; the
configured noisy sample failed the order-18 assertion. Keep issue 32 open
until its live browser acceptance is verified. Required branch-check settings
are an owner action, not something a workflow file can enforce on its own.


## Dispatcher workflow browser regression

The keyless suite exercises the real unlock, Ack and Resolve controls, CSRF
headers, optimistic versions and stored audit. It creates one explicitly
labelled synthetic stored event in a per-run temporary SQLite database and
removes that event afterward. No speech result is fabricated and no mock flag
is added to the application. The private test database is passed explicitly
to the server; the normal developer database is never seeded by this suite.
The live speech suite remains separately opt-in.
