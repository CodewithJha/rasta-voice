# 33 — CI/CD and supply chain

- **Labels:** `day:3`, `deploy`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026). Hook the gates from issues 13 and 32. Closes SEC-06, SEC-07, SEC-08, SEC-09, SEC-15, CFG-04, CICD-01, CICD-02, CICD-03, CICD-04.
- **Depends on:** issue 13 for a Dockerfile to build and scan. Issue 32 for the exact test commands. If 13 has not landed, still add secret scanning, audits, pinning, Dependabot, the PR template, and `CODEOWNERS`; leave the Docker job commented or skipped with a clear `if:`.

## Description

Make `main` and every pull request go through a supply-chain and quality pipeline, still on free GitHub Actions, with no paid scanners.

CI additions to `.github/workflows/ci.yml` (or a small workflow family):

- Reuse issue 32's mypy, pytest+coverage, vitest, and key-less Playwright.
- Secret scanning: `gitleaks` or TruffleHog (free) on the checkout. Fail on a finding. Configure so `.env.example` empty keys do not fire.
- Python audit: `pip-audit` on the installed env. npm: `npm audit --omit=dev` or the current equivalent in `frontend/`. A known issue may be documented in an allow file with an expiry, not ignored in silence.
- SAST: `bandit` on `backend` and `gnani_client`, minus `B101` in tests if needed. Fail on high severity.
- Docker: `docker build` the issue 13 image, then scan with Trivy (free). Fail on CRITICAL/HIGH with a documented exception file if a base-image fix is not yet out.
- Pin Actions to a full commit SHA, with the tag in a comment (`actions/checkout@<sha> # v4.x.x`).
- `concurrency` groups so a new push cancels the previous run on the same branch. No secrets in logs (`secrets` are already masked; still do not `echo` env).

Dependabot: `.github/dependabot.yml` for `pip` (root or the three packages), `npm` (`/frontend`), and `github-actions`, weekly, so the two people can merge bumps.

PR template: `.github/PULL_REQUEST_TEMPLATE.md` with a checklist (issue number, trees touched, tests, no secrets, no mock flag, credit impact, schema freeze). `CODEOWNERS`: Member A for `benchmark/`, `docs/`, `.github/`; Member B for `backend/rasta/`, `frontend/`, `Dockerfile`. The GitHub accounts are `CodewithJha` and the teammate's login if it is already on the repo; if the teammate login is not certain, assign both trees to `CodewithJha` and leave a comment in the file to add the second owner.

CD: a workflow that, on a tag `v*` or on a manual dispatch from `main`, rebuilds the image and prints the steps to update the Space or Render service (`docs/DEPLOY.md`). Auto-push to the host is allowed only with already-stored host secrets and a documented rollback (redeploy the previous tag). If host tokens are not available, the job stops at "image built and scanned" and the runbook (issue 34) has the click path. Do not put `GNANI_API_KEY` in the workflow file.

Pin application versions: add a short note or a `requirements.lock` / `pip freeze` artefact, or tighten lower and upper bounds, so a clean install is reproducible this week (CFG-04). Prefer a lock file generated in this PR.

## Files to touch

- `.github/workflows/ci.yml`
- `.github/workflows/cd.yml` (new, even if manual)
- `.github/dependabot.yml` (new)
- `.github/PULL_REQUEST_TEMPLATE.md` (new)
- `.github/CODEOWNERS` (new)
- `docs/DEPLOY.md` (release and rollback paragraph)
- lock files or tightened ranges as above

## Do not touch

Application logic, frozen schema, frontend visuals. Do not add a paid CI product.

## Input / output contract

A pull request against `main` runs the expanded CI. A commit that adds a fake AWS-looking key in a new file should fail gitleaks (a self-test you can run locally and revert). `trivy` and `pip-audit` reports are visible on the job log.

## Acceptance criteria

- [ ] Actions are SHA-pinned. Concurrency is set.
- [ ] Secret scan, pip-audit, npm audit, bandit, and (when a Dockerfile exists) docker build + Trivy run on pull requests.
- [ ] Issue 32's gates are invoked, or this PR adds them if 32 is late.
- [ ] Dependabot, PR template, and CODEOWNERS exist.
- [ ] CD is documented and at least manually dispatchable. Rollback is a paragraph in `docs/DEPLOY.md`.
- [ ] CI is green on this PR's own workflow with no secrets in the logs.

## How to test

Push a branch, open a PR (or rely on `on: pull_request` and `on: push`), and paste the green run URL in the PR. Run gitleaks locally on a throwaway file, revert it, and show the failed then passing commands.
