# Supply-chain checks

This is the first contract PR for issue 33. It keeps the existing python, web
and contract checks, adds a production frontend build, and introduces four
free checks: secret-scan, audit-python, audit-npm and sast. No live provider
keys or host tokens are used. No application logic or frozen schema changes.

## Local reproduction

Use Python 3.12, Node 22 and a clean environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-ci.lock
pip check
ruff check gnani_client backend benchmark
pytest
python scripts/check_frontend_types.py
bandit -r backend/rasta gnani_client/gnani_client -lll
sed '/^-e /d' requirements-ci.lock > /tmp/rasta-audit-requirements.txt
pip-audit --strict --disable-pip --no-deps -r /tmp/rasta-audit-requirements.txt
cd frontend
npm ci
npm run check
npm run build
npm audit --omit=dev --audit-level=low
```

The audit input contains every pinned third-party runtime, test and scanner
package in the resolved CI environment. Only the three editable local projects
are removed: they are this repository's code and have no published advisory
identity. Their dependencies remain in the input. Dependency collection errors
and vulnerability findings fail the job. There are currently no audit exceptions.
The npm command audits production dependencies; this Vite project currently has
only development dependencies, so it does not audit the build toolchain.

Bandit scans production code, reporting/failing on high-severity findings at
any confidence level. Tests are outside the scan; no assertion suppression is
needed. A clean scan is not a guarantee that all security bugs are absent.

## Secret detection

CI downloads Gitleaks CLI 8.30.1 from its official GitHub release and verifies
the exact archive SHA-256 before extracting it. It does not use a paid action
wrapper. The workflow scans full available Git history, including the PR merge
commit, with findings fully redacted. `.gitleaks.toml` extends all default rules
and adds the Gnani `vach_` key format. Empty `.env.example` values need no bypass.
With the same verified CLI available on PATH, run:

```bash
gitleaks git --config .gitleaks.toml --redact=100 --no-banner .
```

For a detector self-test, create a temporary directory outside the checkout,
write a synthetic AWS-shaped or Gnani-shaped token there, and run `gitleaks dir`
with this repository's absolute config path and `--redact=100`. Expect exit 1.
Remove the token, replace it with an empty example key, and expect exit 0.
Never commit a detector probe, print an unredacted finding or test with a real key.

## Dependency updates

All Actions use verified full commit SHAs with version comments. Checkout does
not persist credentials. Workflow permissions are contents:read, and concurrency
cancels superseded runs on the same ref. Dependabot checks Python inputs at the
root and three packages, npm and GitHub Actions weekly. Both CODEOWNERS remain.

The generated requirements-ci.lock pins third-party versions for Python 3.12.
It includes editable local packages and intentionally is not a hash-locked
artifact. Python package build tooling and the OS/runner remain outside this
lock. Review dependency diffs and regenerate after changing a Python input:

```bash
pip install pip-tools==7.6.2
pip-compile --index-url https://pypi.org/simple --no-emit-index-url \
  --no-emit-trusted-host --no-annotate --output-file requirements-ci.lock \
  requirements-dev.txt requirements-security.txt
```

Run the lock in a clean environment, audit it and rerun all checks before merge.
A Dependabot input bump does not establish that this generated lock was refreshed.
If a future advisory cannot be fixed, review an exception with its advisory ID,
reason, owner and expiry; do not use a blanket `continue-on-error` or ignore list.

## Outstanding issue 33 work

Issue 13 has not supplied a Dockerfile or deployed service. Docker build/Trivy,
CD tag/manual workflows, release tagging and host rollback verification must
follow that implementation. Nothing here deploys, creates a release or certifies
a production host. Issue 32's [quality gates](QUALITY.md) add mypy, an 80% production coverage
floor, Vitest and a real key-less Playwright job. The live browser path remains
opt-in and is not a CI requirement. The deployed API smoke (24), Docker/Trivy
and release/CD still remain; issue 33 stays open.

The four new job names must be added to required branch checks by the repository
owner after this workflow passes on a PR. A workflow file alone cannot change
branch settings. Existing required check names are preserved. Both owners must
agree to this `.github/` contract before merge; do not self-merge it.
