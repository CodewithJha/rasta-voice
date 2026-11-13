# Latency budgets and measurements

These are pass/fail targets for [the k6 harness](../loadtest/README.md), not
claims about a public deployment. A run's exit status and measured error rates
must accompany its p95 values. Connection errors and missing samples cannot
establish a successful latency result.

| Route | Local p95 | Public-host p95 | Load |
| --- | ---: | ---: | --- |
| `GET /api/health` | <100 ms | <300 ms | 20 ops VUs, 30 s |
| `GET /api/ready` | <300 ms | <800 ms | Same ops VUs |
| `GET /api/events`, authenticated | <300 ms | <800 ms | 10 desk VUs, 30 s |
| `POST /api/ingest/sample`, opt-in | <8,000 ms | Staging only; same target | At most 2 VUs, 4 POSTs total |

The readiness target is an additional gate because it checks SQLite and
process readiness. Ops gets health and ready sequentially, then sleeps one
second. Desk unlocks once per VU, polls events and sleeps one second. The
ops and desk error rates must each be at most 1%; when speech is enabled,
every sample must succeed with a correlation ID. Speech is disabled in CI.

Durations use k6's HTTP request duration (sending, waiting and receiving).
They exclude DNS, TCP/TLS connection setup and the intentional think time.
Ops/desk requests time out at 5 s; speech requests time out at 30 s. A public
cold start may fail the run and should be reported separately, not silently
removed from the evidence. Repeat measurements on the actual chosen host
before claiming public readiness.

## Recorded local baseline

Measured on 13 November 2026 (IST), against the real single-worker API from
`8ec65af` on loopback, Python 3.12 and k6 2.4.0. SQLite was file-backed;
the Gnani key was empty and extraction used rules. No provider calls occurred.
The optional upstream-resilience and dispatcher-workflow PRs were not yet
merged, so this is a baseline for that revision, not those future changes.

| Route | Calls | p50 | p95 |
| --- | ---: | ---: | ---: |
| Health | 600 | 4.40 ms | 34.43 ms |
| Ready | 600 | 4.36 ms | 37.78 ms |
| Authenticated events | 300 | 9.89 ms | 74.59 ms |
| Speech | 0 | Not measured | Not measured |

20 ops VUs plus 10 desk VUs ran for the configured 30 seconds. Both error
rates were 0; all thresholds passed and k6 exited 0. This does not measure a
crowded public host or live speech latency. A separate closed-port run had
ops error rate 1, failed thresholds and exited 99, demonstrating the failure
path. Synthetic loopback fixture tests separately verify the speech-call cap
and early aborts; they are not Gnani performance measurements.

Re-run the baseline after changes to readiness, storage, middleware or the
host. Preserve the tested revision, VU counts, duration, error rates and
whether speech actually ran. Issue 33 owns the CI hook; deployed smoke,
real speech latency and a public-host baseline remain separate evidence.
