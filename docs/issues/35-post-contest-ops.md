# 35 — Post-contest operations stretch

- **Labels:** `day:post-contest`, `docs`, `deploy`
- **Owner:** Member A: Himanshu (@himanshu748), benchmark & audio (Member B: Priyanshu Jha (@CodewithJha) reviews anything that touches `backend/` or `frontend/`)
- **Target day:** After **15 Nov 2026, 18:00 IST**. Do not start this during the contest window if it would delay issues 16 or 18, or any P0. Closes OBS-03, the P2 half of OBS-04, FE-08, OPS-05, DATA-03's off-site half, CICD-03's automated release stretch.
- **Depends on:** a production-ready `main` (P0 issues merged) and a live host from issue 13. This issue is optional for the contest score.

## Description

Work that a longer-lived production service would want, and that a two-person team on one free host cannot honestly finish before the deadline.

Out of scope for the contest, in scope here:

- A second free host (a second Space or Render service) as **staging**, with its own secrets, a smaller credit budget, and the same image tag as production minus the public social URL.
- Off-site SQLite backup: a scheduled export of the database (transcripts already redacted by issue 28) to a free object store the team already has, with a tested restore drill. If no free store is available, a documented manual export remains the fallback and this bullet stays open.
- A self-hosted or free-tier error tracker (for example GlitchTip) and, if useful, an OpenTelemetry exporter to a free collector. Do not pay. Do not break issue 21's "no secrets in logs" rule. The in-process usage panel from issue 25 stays the default if this is too heavy for the host.
- Production source-map policy: upload maps to the tracker, do not serve them at the public origin.
- Automated release tagging (`vX.Y.Z`), changelog extraction, and a CD job that deploys the tag to staging, waits for `/api/ready`, then deploys production with a one-click rollback to the previous tag.
- Horizontal scale: only after leaving SQLite, which is a real design change and needs a new ADR. Until then, the runbook's "one worker" rule stands.

Do not add a mock mode, a paid APM, or a second production database during the contest in the name of this issue.

## Files to touch

- `docs/adr/0005-staging-and-backup.md` (new, when you start)
- `docs/RUNBOOK.md` (staging, backup drill, rollback of tags)
- `.github/workflows/` CD extensions
- backend/frontend only as needed for map policy or a trace exporter, in a separate PR, after the deadline

## Do not touch

Contest submission files, the frozen schema, the "no mock mode" rule, the public video claims.

## Input / output contract

A staging URL that serves `/api/ready` with `ok: true` and its own passcode. A backup tarball that restores into a local `RASTA_DB_PATH` and shows the same event ids. A tag that can be deployed and rolled back once, documented in the changelog.

## Acceptance criteria

- [ ] Staging exists or the issue explains which free host was refused and what was used instead.
- [ ] A backup-and-restore drill is written and has been run once, with a date.
- [ ] Error tracking or tracing, if added, is free and does not log secrets or audio.
- [ ] Public origin does not serve `.map` files.
- [ ] Tag, changelog, and rollback have been exercised once.

## How to test

Run the restore drill on a throwaway database. Hit staging `/api/ready`. Deploy a tag, then roll it back, and record the four timestamps in the runbook.
