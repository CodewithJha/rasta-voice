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

## Production image and release handoff

The issue 13 Dockerfile now has a separate production-only
`requirements-runtime.lock`, generated from the two runtime package inputs.
The image installs these pinned dependencies, then installs the local client
and backend with `--no-deps`. It retains the lock inside `/app`. The benchmark,
test tools and scanners are not runtime dependencies. As with the CI lock,
these are version pins, not hash locks; base images, pip and build tooling
remain outside this application dependency lock.

The first real image scan rejected the previous Bookworm runtime for OS
HIGH/CRITICAL advisories and its unused setuptools 70.3.0 for
CVE-2025-47273 (fixed in 78.1.1). The runtime now uses the official
`python:3.12-alpine3.24` image with current APK updates, retains UID 1000,
and removes pip, ensurepip and setuptools/wheel after installing the local
packages and running `pip check`. Pip's unused vendored setuptools also
carried the advisory, so uninstalling standalone setuptools alone was not
sufficient. Runtime dependencies are still discoverable through their
standard package metadata; the image smoke checks every locked version,
audio imports and a file-backed SQLite write/reopen as UID 1000. The Node
build stage remains separate. This base change must pass the same real
image smoke and unfiltered HIGH/CRITICAL scan; it is not an exception.

Regenerate the runtime lock deliberately after a runtime input changes:

```bash
pip-compile --index-url https://pypi.org/simple --no-emit-index-url \
  --no-emit-trusted-host --no-annotate --output-file requirements-runtime.lock \
  gnani_client/pyproject.toml backend/pyproject.toml
```

`.github/workflows/cd.yml` runs a `container` check on pull requests, main
pushes, version tags (`v*`) and manual dispatches from main. It builds the
actual multi-stage image, verifies its non-root user, starts it with a
synthetic test passcode and an explicitly empty speech key, and checks
health, built JS/CSS assets, desk protection and the missing-key HTTP 503.
It sends one keyless sample POST, never a configured speech request. The
test container is removed even after failure.

The same job downloads Trivy CLI 0.76.2 from its
[official release](https://github.com/aquasecurity/trivy/releases/tag/v0.76.2)
and verifies the archive SHA-256 before running it. It scans OS and library
packages in the built image and fails on HIGH or CRITICAL findings, including
unfixed ones. No blanket ignore or `continue-on-error` is configured. Any
future exception needs the advisory, affected package, reason, owner and
expiry reviewed in the PR. Scan/download failures also fail the job.

Tag and main/manual runs print the [deployment and rollback handoff](DEPLOY.md).
There is no image-registry push, host token, provider key, automatic host
update or release creation. A successful job proves this revision built,
passed the keyless image checks and passed the configured vulnerability
scan; it does not prove a working public host or live provider path.

Issue 32's [quality gates](QUALITY.md) still run independently. The live browser
path remains opt-in. Public smoke (24), a real release/host rollback exercise
and owner configuration of required branch checks remain outstanding; issue
33 stays open until those remaining acceptance checks are verified.

The added job names, including `container`, must be added to required branch checks by the repository
owner after this workflow passes on a PR. A workflow file alone cannot change
branch settings. Existing required check names are preserved. Both owners must
agree to this `.github/` contract before merge; do not self-merge it.

## Verified source-digest false positive, 14 November 2026

Gitleaks scans every available ref after the full-history checkout, including
other open PR branches. A generic-api-key finding in integration commit
`4f609e171d4ba4fa64fbedb6ab70332a1131d8b5`, line 9 of
`docs/evidence/integration-2026-11-14.json`, is a source SHA-256 beside the
`backend/rasta/dispatch_auth.py` property. Recomputing the digest of that
source file at the same commit exactly matches the recorded value. It is
public source provenance, not a credential. The current integration evidence
separates path and digest fields.

`.gitleaksignore` records only that immutable commit/file/rule/line fingerprint.
No detector, file path, token prefix or future commit is excluded. This record
is also needed by unrelated PRs because their full checkout includes the
integration ref. Owner: Himanshu (`himanshu748`); review by 21 November 2026.
The detector still rejects a synthetic Gnani-shaped probe with exit 1 and
accepts an empty example with exit 0; no real credential was used.
