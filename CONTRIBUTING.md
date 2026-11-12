# Contributing to Rasta Voice

Two people work in this repository at once. Member A owns `benchmark/` and the benchmark docs. Member B owns `backend/rasta/` (except the frozen schema), `frontend/`, and `Dockerfile`. Frozen for both: `gnani_client/`, `shared/rider_event.schema.json`, `backend/rasta/schema.py`, `frontend/src/types.ts`. Do not restyle the other person's screen. A later docs pack (issues 23 and 34) will extend this file; the workflow below is the rule now.

## Workflow

1. **Branch naming.** Start from an up-to-date `main`. Name the branch `issue-NN-slug`, for example `issue-01-utterance-corpus` or `issue-02-llm-extractor`.
2. **One issue per pull request.** Small pull requests. If a contract has to change, that change goes first in its own pull request (see below), and the feature follows after it is merged.
3. **Never push to `main`.** Open a pull request and wait for review and the required checks (`python`, `web`, `contract`).
4. **Sync before you push.** Run `git pull --rebase origin main` so your branch is current. If the rebase stops on a conflict, fix it locally (see below), then `git rebase --continue` and push.
5. **Checks locally** before you open or update a pull request:

   ```bash
   ruff check gnani_client backend benchmark
   pytest
   python scripts/check_frontend_types.py
   cd frontend && npm run check
   ```

6. **Contract changes go first.** A change to `shared/`, `backend/rasta/schema.py`, `frontend/src/types.ts`, `gnani_client/`, or `.github/` is a contract pull request. Keep it small. Both people should agree on it before it merges, even though GitHub asks for one approving review. Then rebase the feature branch onto `main`.
7. **Twice-daily sync.** At least twice a day, rebase onto `origin/main` and leave a one-line note on your open issue (what landed, what is blocked). That is enough for the other person to stay out of your files and not be surprised.
8. **Squash merge.** Use GitHub's squash merge. The squash commit subject should be the pull request title, written as a conventional commit (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `ci:`). Delete the branch after the merge.
9. **Commit identity.** Each person commits as their own GitHub account (name and `users.noreply.github.com` email). Do not add `Co-authored-by` trailers, and do not attribute a commit to anyone who did not make it.

## Trees

Stay inside your tree unless the issue says otherwise. If a client bug in `gnani_client/` blocks you, fix it in a contract pull request and say so in the body. Do not edit the other person's in-flight files (`frontend/src/rider.ts` is a common collision; one pull request at a time).

## Frozen contracts

`shared/rider_event.schema.json`, `backend/rasta/schema.py`, and `frontend/src/types.ts` must change in the same contract pull request. The `contract` check on CI will fail if they drift. Do not add fields to `RiderEvent` without updating all three, and do not put lifecycle or envelope fields inside the frozen event object.

## Conflict resolution

1. `git fetch origin` and `git pull --rebase origin main`.
2. If git stops, open the listed files, keep both sides of the work where they do not overlap, and do not silently drop the other person's lines.
3. Re-run the local checks.
4. `git add` the resolved files, `git rebase --continue`, then `git push --force-with-lease` (only after a rebase of your own branch).
5. If the conflict is in a frozen contract file, stop and agree the contract pull request first. Do not resolve a schema conflict by inventing a third shape.

If `main` moved under you and the pull request shows "branch is out of date", rebase and push again. Required status checks are strict: the branch must be up to date with `main` before merge.

## Line endings and optional hooks

`.gitattributes` forces `lf` for text files. `.editorconfig` matches that (spaces, a trailing newline, trim whitespace).

[pre-commit](https://pre-commit.com/) is **opt-in**. It runs ruff, end-of-file, and trailing-whitespace hooks. It is not required for CI, which already runs ruff and the tests.

```bash
pip install pre-commit
pre-commit install
# or a one-off run:
pre-commit run --all-files
```

## Rules that apply to every change

- Synthetic audio and synthetic order tokens only. No real phone numbers, call recordings, customer names, or government IDs.
- Free tools only.
- Real Gnani calls only in app and benchmark code. No mock flags, canned transcripts, or fixture scores. Tests may swap the HTTP transport with `httpx.MockTransport` inside the test file. A missing `GNANI_API_KEY` is a loud error, never a silent fallback.
- Do not commit `.env` or any secret.
