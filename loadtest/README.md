# Local load checks

Run from the repository root with the free [k6 CLI](https://grafana.com/docs/k6/latest/set-up/install-k6/).
The verified development version is k6 2.4.0. There are no remote JavaScript
imports, paid load services or provider keys in this harness.

Start the real API in one terminal, using a writable temporary SQLite file,
`LLM_PROVIDER=rules`, an empty `GNANI_API_KEY`, and a synthetic
`DISPATCH_PASSCODE`. Use the normal development startup from the README.
Then run, in another terminal on the same machine:

```bash
K6_NO_USAGE_REPORT=true k6 run loadtest/k6.js \
  -e BASE_URL=http://127.0.0.1:8000 \
  -e DISPATCH_PASSCODE="$DISPATCH_PASSCODE"
```

Ops always runs at 20 virtual users for 30 seconds. Each iteration gets
`/api/health` and `/api/ready`, then sleeps one second. When the passcode is
set, another 10 VUs unlock once each and poll `/api/events` for 30 seconds.
Cookie jars stay separate per VU and persist between its iterations. An unlock
failure aborts the run. There are no desk actions or application data writes
apart from the API's normal readiness/store behavior.

The JSON console summary contains request counts, p50/p95 durations in
milliseconds, error rates and threshold results. `SUMMARY_PATH` optionally
writes the same selected metrics to a JSON file. The configured 30 seconds
and actual elapsed time are separate; an aborted run is not a 30-second result.
The command's exit status is authoritative, including an early abort.

Loopback selects the local budgets; other origins select the public budgets.
`PROFILE=local` or `PROFILE=public` can select one explicitly. See
[the measured baseline and budgets](../docs/SLO.md). Incorrect HTTP statuses,
invalid JSON and unhealthy readiness count as failures, not fast successes.
The error-rate limits include both health and readiness in ops, and unlocks
and event reads in desk. Missing latency samples fail the relevant count gate.

## Negative check

```bash
K6_NO_USAGE_REPORT=true k6 run loadtest/k6.js -e BASE_URL=http://127.0.0.1:9
```

With that port closed, expect a non-zero exit and an ops error rate of 1.
This is a threshold failure; the script does not treat connection-refused
durations of zero as proof that the service met its latency budget.

## Optional speech

Speech is off unless `SPEECH=1`. Do not enable it for the contest origin.
It is rejected in CI, even on loopback. Allowed targets are exactly localhost,
127.0.0.1, ::1, or an HTTPS origin whose hostname contains a separate `stage`
or `staging` label/segment and exactly matches an explicit `STAGING_BASE_URL`.
Origins cannot contain credentials, URL paths, query strings or fragments.

```bash
# Only after configuring a small host speech budget and checking its balance:
K6_NO_USAGE_REPORT=true k6 run loadtest/k6.js \
  -e BASE_URL=http://127.0.0.1:8000 -e SPEECH=1
```

The shared-iterations scenario uses at most two speech VUs and four sample
POSTs across the whole single-process run. Redirects and harness retries are
disabled. Each success must carry `X-Request-ID`. A 429, other failure or
missing correlation header aborts the whole test; a second VU already
outbound cannot be recalled. Do not launch copies in parallel or override
the scenario configuration.

Four sample POSTs normally mean eight Gnani calls (Timbre plus Prisma).
Server-side retries can add charged attempts. The host's global budget must
remain the final cap; this script does not rotate, reset or bypass it. The
8-second speech p95 applies only when measured, never to a skipped scenario.

## Safety regression checks

```bash
node --test loadtest/tests/config.test.mjs
python loadtest/tests/safety.py --k6 /path/to/k6
```

The Node tests reject unsafe origins and CI speech before any HTTP request.
The second command runs the real k6 executable against a test-only loopback
HTTP fixture. It verifies exactly four sample POSTs with at most two active,
and non-zero exits after a missing ID or a 429. Its successful case runs the
same 30-second ops scenario. It never calls Gnani or uses an application mock
mode. Its response times are safety-test results, not app latency evidence.

## CI gate (issue 33)

`.github/workflows/load.yml` runs the `load` job on pull requests and main.
It checks the offline guards, installs checksum-verified k6 2.4.0 and invokes
`loadtest/ci.py`. The helper boots the real API, waits for SQLite readiness,
runs the 20/10-VU test and verifies a closed-port run fails with exit 99.
It forces an empty speech key, `CI=true` and `SPEECH=0`, confirms zero sample
calls and unchanged credits, and terminates its API process in `finally`.
Selected metrics appear in the job summary, including on failure. A passing
job does not prove public-host or live-speech performance. Adding `load` as
a required branch check remains an owner configuration step.

For local reproduction with k6 on PATH and the API dependencies installed:

```bash
python loadtest/ci.py --k6 /path/to/k6 --output-dir /tmp/rasta-load-results
```

The helper keeps the API and k6 in the same process tree, so it also works
in environments that isolate networking between separate shell sessions.

Start the API from `requirements-ci.lock` with a temporary `RASTA_DB_PATH`,
`LLM_PROVIDER=rules`, an empty speech key and a synthetic desk passcode. Wait
for real `/api/ready` to return 200 before starting k6. Run the normal command
above with `CI=true` and `SPEECH=0`, retain the exit code and selected JSON
summary, and terminate the API on failure as well as success. Install k6 from
its official release and verify the release archive checksum. The container
check remains separate from this load gate.

Do not use HTTP debug output, print request bodies/cookies, copy a real desk
passcode into a script, or upload a general environment dump with the results.
`K6_NO_USAGE_REPORT=true` disables k6's anonymous usage reporting.
