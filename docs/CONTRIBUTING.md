# Contributing

The root [CONTRIBUTING.md](../CONTRIBUTING.md) is the workflow authority;
[PLAN.md](PLAN.md) assigns the work. The team has two members: Himanshu
(`@himanshu748`, Member A) and Priyanshu Jha (`@CodewithJha`, Member B).

| Tree | Implementation owner |
| --- | --- |
| `benchmark/` and benchmark documentation | Himanshu, Member A |
| `backend/rasta/` except its frozen schema | Priyanshu, Member B |
| `frontend/` and `Dockerfile` | Priyanshu, Member B |

An issue can explicitly assign a narrow exception, as issue 08 did for the
reply route. State that exception in the PR. Coordinate before editing the
other member's in-flight files, especially `rider.ts`. Preserve the product's
existing visual design; a backend or docs task is not permission to restyle it.

`gnani_client/`, `shared/rider_event.schema.json`, `backend/rasta/schema.py`,
`frontend/src/types.ts` and `.github/` are frozen/shared review surfaces.
Contract changes land separately before dependent features. Event-schema
changes update all three schema/type representations together and require
both members' agreement. Envelope metadata stays outside `RiderEvent`.

Start from current `main`; use `issue-NN-slug` and one issue per PR. Rebase
before pushing and after the base advances, resolve conflicts without
discarding the other member's tests, and rerun relevant checks. Do not push
or force-push to `main`. Explain the concrete behavior, trees touched,
validation and credit impact in the existing
[PR template](../.github/pull_request_template.md). Never include secrets.

Run from the repository root:

```bash
ruff check gnani_client backend benchmark
pytest
python scripts/check_frontend_types.py
cd frontend && npm run check
```

Use `npm run build` to verify frontend production output when it changes.
The required CI jobs are `python`, `web` and `contract`; all must pass and
the other member must review before squash merge. The existing
[CODEOWNERS](../.github/CODEOWNERS) lists both members on every path, including
shared contracts; preserve both names so a PR always has another eligible
reviewer. Coverage/type/Playwright gates are still issue 32, and expanded
supply-chain/CD checks are issue 33. Do not describe those as existing gates.

Tests may replace HTTP transport with `httpx.MockTransport` inside test files.
Production application and benchmark code always call real Gnani APIs, or
reuse explicitly provenance-checked cached results; there is no mock mode,
canned transcript path or fixture score. A missing speech key is an explicit
failure. Live tests are opt-in, need an authorized key and a known credit
budget, and must not expose credentials or fabricate successful output.

Use short imperative conventional commit subjects (`feat:`, `fix:`, `docs:`,
`test:`, `chore:` or `ci:`) and explain material context in an optional body.
Commit as the person who did the work using that person's GitHub noreply
identity. Do not add co-author trailers or attribute work to a third person.
Leave a short sync/status note on the open issue, keep existing labels and
assignees, squash merge after review, and delete the merged branch.

Issue 34 owns LICENSE, CHANGELOG, CODE_OF_CONDUCT, ADRs and the operator
runbook. Add links when those files land; this page does not claim they exist.
