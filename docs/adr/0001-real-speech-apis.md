# ADR 0001: Real speech APIs only

Status: Accepted. Date: 13 November 2026.

## Context

The demo and benchmark must show what Gnani actually transcribes and speaks.
A silent fake transcript would hide missing configuration and invalidate results.

## Decision

Use real Prisma for STT and Timbre for synthesis. Missing speech configuration
fails visibly (503); upstream errors remain errors. Do not add a mock app mode,
canned provider output or fixture benchmark scores. Tests may replace the HTTP
transport inside test code. Synthetic input audio is allowed and disclosed.

## Consequences

Live samples spend credits and require network access. Keep keys server-side;
run ordinary tests without live calls. Cache only provenance-backed completed
outputs and distinguish controlled noise from real field evidence.

See [architecture](../ARCHITECTURE.md) and [runbook](../RUNBOOK.md).
