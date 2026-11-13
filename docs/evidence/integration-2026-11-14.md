# Integrated candidate verification, 14 November 2026 IST

This is code and local/CI evidence, not a declaration of a public deployment,
field consent or contest submission. The original benchmark block is preserved
byte-for-byte; its SHA-256 and critical source hashes are in the adjacent JSON.
Local commit IDs identify the freeze before browser uploads create different
GitHub commit IDs. Content hashes allow comparison after upload.

The candidate combines Priyanshu's privacy/API work from PRs 83 and 85, the
response policy already merged in 84, the bounded upload and CSRF slices in
86/87, and the focused privacy/API review repairs in 88/89. It also includes
labelled rule-context development regressions and a real keyless desk-workflow
browser test. These components still need their required owner reviews and
merged-state verification. Issue ownership and labels are unchanged.

## Local verification

| Check | Measured result |
| --- | --- |
| Full Python suite | 1,854 passed, 1 skipped, 1 expected failure |
| Line coverage | 90.93%; enforced floor remains 80% |
| Ruff | Clean across production packages and scripts |
| Mypy | Clean on 57 production source files |
| Frontend | Source/test types, 4 Node tests, 23 unit tests and build pass |
| Runtime dependency inputs | Same audited pinned locks as the upload slice |
| Browser | Local launch blocked by a denied socket; final GitHub browser job must verify the candidate |

The expected failure is the unmet issue 2 holdout-accuracy target. It is not a
waiver or an LLM success. The live speech path is skipped without a key. All
checks in this pass are keyless; no live provider requests were made.

## Combined boundaries

Tests cover tokenless versus valid-cookie CSRF writes, exact session binding,
versioned aliases, expired transitions and legacy redaction. A cached reply
cannot outlive its event's TTL. Delete, wipe, TTL purge and eviction clear
associated replay payloads while retaining non-sensitive no-repeat metadata.

Concurrent identical keys do not launch duplicate speech work. Keyed bodies
are bounded before accumulation and at most 16 can be buffered concurrently.
Definite budget/rate/concurrency denials release their claim without filling
the SQLite replay ledger; admitted uncertain work retains its no-repeat outcome. Interrupted or uncertain outcomes cannot
silently repeat paid work. Replay bodies are memory-only and bounded; their
SQLite ledger contains hashes and status, not transcripts or base64 audio.
The revised storage contract and restart/eviction failure behavior require
owner review in PR 89.

Replays cross Trusted Host, CORS, error-normalization, response-header and
usage-counting boundaries. Cached errors carry the current HTTP request ID.
Removing the server key prevents an old successful speech response from being
served. A production-config regression verifies both host rejection and
allowed-origin response headers on replay.

The keyless browser workflow uses one labelled stored test event in a per-run
temporary database. It exercises real unlock, polling, Ack, Resolve, CSRF,
If-Match versions and the audit trail. It does not impersonate a Gnani result.

## Load results

Both runs use 20 ops VUs and 10 desk VUs for 30 seconds, zero speech VUs and
the existing local thresholds. The first combined run failed the health
latency target. The final candidate removes avoidable thread-pool hops in
cheap prechecks and health; the thresholds were not changed.

| Metric | First combined run, p95 | Final candidate, p95 | Local limit |
| --- | --- | --- | --- |
| Health | 169.10 ms | 20.49 ms | 100 ms |
| Readiness | 76.32 ms | 64.44 ms | 300 ms |
| Desk polling | 182.44 ms | 51.55 ms | 300 ms |

Final requests: 600 health, 600 readiness and 300 desk polls. Ops and desk
error rates were zero, speech calls were zero and the configured credit
budget was unchanged. The closed-port negative produced exit 99 with failed
thresholds and zero speech. Full machine-readable measurements, including
the failed first run and earlier passing async run, are preserved in the JSON.
The final run follows the last API capacity/admission commit.

These are local short-run measurements on an empty synthetic desk, not a
public-host SLO guarantee or a live speech latency benchmark.

## Remaining acceptance

- Required peer/code-owner reviews, prerequisite merges and final combined CI.
- A verified free-host origin and deployed SHA, followed by bounded public
  smoke and a real rollback check; no hosting workspace was selected.
- Owner-side enforcement of the documented branch settings.
- Locked rules accuracy is 8/36, below 0.8; no model result is invented.
- Real consented field recordings, the measured script read-through, playable
  public video/posts and confirmed form submission.
- Issue 35's post-contest infrastructure remains unfinished.

Keep public speech paused until its release prerequisites are verified.
