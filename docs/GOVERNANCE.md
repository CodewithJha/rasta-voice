# Governance and branch protection

Himanshu Kumar (@himanshu748, Member A) owns benchmark/audio work. Priyanshu
Jha (@CodewithJha, Member B) owns the application and deployment. See the
[root workflow](../CONTRIBUTING.md) and [contributor guide](CONTRIBUTING.md).
One issue per PR, review by the other owner, then squash merge. Neither owner
merges their own PR. Both agree to frozen contract changes before merge.

## Required main-branch policy

Require a pull request, one approval from the other code owner, dismissal of
stale approvals, passing `python`, `web` and `contract` checks, and an up-to-date
branch. Disallow force pushes and branch deletion. Apply protections to
administrators and avoid bypasses. CODEOWNERS alone does not enforce this.

In GitHub repository **Settings > Branches > Add branch protection rule**, use
`main`, enable **Require a pull request before merging**, **Require approvals**
(1), **Dismiss stale pull request approvals when new commits are pushed**, and
**Require review from Code Owners**. Enable **Require status checks to pass
before merging**, select the three check names above, and **Require branches
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
are disabled. Administrator enforcement (`enforce_admins`) is **false**, so
administrators can bypass the rule. This is reported owner verification, not a
settings change made by this PR. Keep issue 34 open until that bypass is disabled
or both owners explicitly record acceptance of the limitation. This document
does not accept it on their behalf.

License and conduct changes require both owners' agreement. The MIT license
and conduct policy are merged through PR 50; this update changes neither.
The administrator-bypass limitation above remains unresolved on issue 34.
