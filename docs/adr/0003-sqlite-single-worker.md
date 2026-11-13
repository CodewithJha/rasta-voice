# ADR 0003: SQLite with one worker on a free host

Status: Accepted for the merged single-worker implementation. Updated: 13 November 2026.

## Context

PR 75 replaced volatile event history with a file-backed SQLite store. PR 71
prepared the free-host image, while the public origin remains unpublished.
Rate limits, credit reservations, stream slots and caches remain process-local.

## Decision

Run one application worker and one replica. Store events at RASTA_DB_PATH,
default data/rasta-events.sqlite (the image uses /app/data). Boot migrations,
WAL and the configured event cap belong to the store implementation. Use the
protected /api/admin/export online-backup snapshot for an operator download.
Multiple workers or replicas need a separately reviewed shared-state design.

## Consequences

A restart on the same disk retains events but resets process-local controls.
Free-host rebuilds can erase the disk. A downloaded snapshot is not an automatic
off-site backup; issue 35 owns that work. The non-root image and SQLite tests
are merged, but an actual public deployment, restore and rollback still require
host verification. This decision does not certify those unperformed actions.

See [runbook](../RUNBOOK.md), [deploy](../DEPLOY.md) and
[governance](../GOVERNANCE.md).
