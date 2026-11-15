# Governance and branch protection

Himanshu Kumar (@himanshu748, Member A) owns benchmark/audio work. Priyanshu
Jha (@CodewithJha, Member B) owns the application and deployment. See the
[root workflow](../CONTRIBUTING.md) and [contributor guide](CONTRIBUTING.md).
One issue per PR, review by the other owner, then squash merge. Neither owner
merges their own PR. Both agree to frozen contract changes before merge.

## Required main-branch policy

Require a pull request, one approval from the other code owner, dismissal of
stale approvals, all ten checks below, and an up-to-date branch. Disallow
force pushes and branch deletion. Apply protections to
administrators and avoid bypasses. CODEOWNERS alone does not enforce this.

| Workflow | Required check names |
| --- | --- |
| `ci` | `python`, `web`, `contract`, `secret-scan`, `audit-python`, `audit-npm`, `sast`, `browser-smoke` |
| `container` | `container` |
| `load` | `load` |

In GitHub repository **Settings > Branches > Add branch protection rule**, use
`main`, enable **Require a pull request before merging**, **Require approvals**
(1), **Dismiss stale pull request approvals when new commits are pushed**, and
**Require review from Code Owners**. Enable **Require status checks to pass
before merging**, select all ten check names above, and **Require branches
to be up to date before merging**. Enable **Do not allow bypassing the above
settings**; leave **Allow force pushes** and **Allow deletions** disabled.
Save, reopen the rule, and record the settings here. Equivalent rulesets may
be used if the repository owner verifies the same effective policy.

## Verification record: 13 November 2026

The PR interface requires code-owner approval and all three checks, blocks
out-of-date branches, and dismissed an approval when PR 47 changed. These
behaviors were observed during review. The rulesets endpoint returned no
rulesets; classic branch protection may still apply. The integration returned
403 for the classic protection API, so a complete settings audit could not be
performed through it. No setting was changed by this documentation PR.

Priyanshu inspected the classic protection rule during review of PR 50 on
13 November 2026: PRs, one code-owner approval, stale-approval dismissal, all
three checks and an up-to-date branch are required. Force pushes and deletion
were disabled. Administrator enforcement (`enforce_admins`) was **false** at that
time, allowing administrators to bypass the rule. This historical owner report
required disabling that bypass or recording both owners' acceptance. The
15 November record below resolves it by disabling the bypass.

License and conduct changes require both owners' agreement. The MIT license
and conduct policy are merged through PR 50; this update changes neither.

## Verification update: 15 November 2026

The expanded workflow runs all ten checks successfully on PR 102, including
the production image build and Trivy scan. Its code-owner approval and squash
merge were performed by Priyanshu. This proves the jobs ran and peer review
occurred, not that all ten jobs are required by the effective protection rule.

Himanshu's collaborator browser receives 404 for repository Settings > Branches.
The connected GitHub integration returns 403, `Resource not accessible by
integration`, for upstream write operations and does not have administration
access. Collaborator browser access still permits normal reviews and pull
requests. Neither route grants permission to administer the protection rule.

After merging PR 103, Priyanshu applied and re-read the classic `main` branch
protection rule as repository owner. His
[verification on issue 34](https://github.com/CodewithJha/rasta-voice/issues/34#issuecomment-6889687411)
records the following saved settings:

- A pull request, one approving review, code-owner review and dismissal of stale reviews.
- An up-to-date branch and all ten required check names in the table above.
- Administrator enforcement (`enforce_admins: true`).
- Force pushes and branch deletion disabled.
- Conversation resolution and linear history required.

Priyanshu reports that the protection API returned these values after save.
This is the repository owner's verification; Himanshu's integration still
does not have administration access. It supersedes the 13 November settings
record and resolves the administrator-bypass limitation without accepting a
bypass. Live speech, field consent and rollback evidence retain their separate
release gates; branch protection does not establish those results.
