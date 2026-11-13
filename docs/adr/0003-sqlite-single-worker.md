# ADR 0003: SQLite with one worker on a free host

Status: Proposed, blocked by issues 19 and 13. Date: 13 November 2026.

## Context

Current events live in an in-process ring and disappear on restart. Separate
workers have separate stores and stream/reply limits, even before SQLite lands.

## Decision proposed

Use SQLite with one application worker for the free-host demo. Choose and
validate its database path and migration/retention behavior in issue 19. Do not
run multiple workers against the proposed SQLite deployment. A future scale-out
change needs a shared store and shared concurrency/credit controls.

## Consequences

Today, use one worker and expect total history loss on restart. No database path
setting or backup command is implemented yet. Future SQLite survives a process
restart only while its disk remains; free-host disk can disappear. Off-site
backup is issue 35. Accept this ADR only after the persistence/deployment PRs
land and their startup/backup steps are verified.

See [runbook](../RUNBOOK.md) for current behavior and conditional backup steps.
