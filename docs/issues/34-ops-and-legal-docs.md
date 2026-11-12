# 34 — Operations and legal docs

- **Labels:** `docs`, `day:3`
- **Owner:** Member A: Himanshu (@himanshu748), benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026), after 23 so you can link, not rewrite, architecture and security. Closes DOC-01, DOC-02, DOC-03, DOC-04 (link), OPS-01, OPS-02, OPS-03, OPS-04, OPS-06, ARCH-04, DATA-03 (document), SEC-15 (branch protection *policy*), CFG (operator list of env vars).
- **Depends on:** issue 23. Write only what is true on `main` the day you merge, same rule as 23. If 25–33 have not all landed, say so.

## Description

Give operators and judges the documents a public production repo is expected to have.

`LICENSE` at the repo root. A standard free licence (MIT or Apache-2.0) is enough. Himanshu and Prakhar must both be comfortable with the choice; if they have not picked, use MIT and name the copyright holders as Himanshu (@himanshu748) and Prakhar (@CodewithJha). Do not invent a third owner.

`CHANGELOG.md` following Keep a Changelog, with an `Unreleased` section and, once a tag exists (issue 33), a `0.1.0` or `0.2.0` entry. Credit-impacting changes get a line.

`CODE_OF_CONDUCT.md`, Contributor Covenant or a one-page equivalent, with a contact path that is a GitHub issue or an email already used by the team, not a new paid tool.

`docs/adr/`: at least four short ADRs, one page each: (1) real Gnani APIs only, no mock mode; (2) frozen `RiderEvent` with envelope extensions; (3) SQLite and one worker on a free host; (4) shared desk passcode rather than a user database. Link them from issue 23's architecture doc.

`docs/RUNBOOK.md`:

- How to boot local and production, with the full env list from `.env.example`.
- One-worker topology (do not run `--workers 2` against this SQLite).
- Credit exhaustion: how it looks (`/api/ready`, 429, Gnani 402), how to pause public speech (remove the sample button by setting a budget of 0, or take the Space offline), how to rotate `GNANI_API_KEY` and `DISPATCH_PASSCODE` on the host, what to say on the social post if the demo is paused.
- Incident notes: copy `/api/ready`, `X-Request-ID`, recent JSON logs, and the usage endpoint. Do not copy secrets or raw audio.
- Rollback: previous image tag or previous `main` commit on the Space, per issue 13/33.
- Backup: how to download the SQLite file from the host if the disk is still there; honest note that free-host disk is ephemeral (issue 19) and that off-site backup is issue 35.
- SLOs: link `docs/SLO.md` from issue 31 if it exists.

Branch protection: a short `docs/GOVERNANCE.md` or a section in `CONTRIBUTING.md` that says `main` should require a PR, a green CI, and no force-push. You cannot flip GitHub settings from a file; write the required clicks and tick this issue only when someone has applied them or has honestly recorded that they could not (no org permission).

Link all of the above from the README, next to issue 23's three docs. Do not claim features that are still open issues.

## Files to touch

- `LICENSE`, `CHANGELOG.md`, `CODE_OF_CONDUCT.md` (new)
- `docs/adr/0001-*.md` … `0004-*.md` (new)
- `docs/RUNBOOK.md` (new)
- `docs/CONTRIBUTING.md` or `docs/GOVERNANCE.md` (branch protection)
- `README.md` (links only)
- `docs/API.md` only if 26 has not written it and you need a stub that points at OpenAPI

## Do not touch

Application code, frozen schema, frontend visuals, benchmark scores.

## Input / output contract

A newcomer can follow README → RUNBOOK and know how to start the app, where secrets live, what to do on 402, and how to roll back, without reading the issue tracker.

## Acceptance criteria

- [ ] LICENSE, CHANGELOG, CODE_OF_CONDUCT, four ADRs, and RUNBOOK exist and are linked from the README.
- [ ] RUNBOOK covers credit exhaustion, rollback, one-worker topology, and the ephemeral-disk warning.
- [ ] ADRs match the merged code and the "no mock mode" rule.
- [ ] Branch-protection clicks are documented, and applied or honestly deferred.
- [ ] No API keys, passcodes, or personal phone numbers in these files.

## How to test

Read the RUNBOOK against a local boot and against `docs/DEPLOY.md`. Click every README link. Ask Prakhar (Member B) to skim LICENSE and the conduct file before merging.
