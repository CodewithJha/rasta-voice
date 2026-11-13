# ADR 0004: Shared desk passcode instead of a user database

Status: Proposed, blocked by issue 20. Date: 13 November 2026.

## Context

The two-person demo needs limited desk access without building account signup,
password recovery or a user database. Current GET /api/events is public.

## Decision proposed

Use a server-side shared desk passcode for the demo, with authenticated access
and rate/expiry controls defined and reviewed in issue 20. Do not embed the
secret in built JavaScript, a URL or committed configuration. Keep the rider's
public controls distinct from protected desk access as that contract specifies.

## Consequences

A shared secret cannot identify individual operators and rotation affects every
desk. Current main does not read DISPATCH_PASSCODE and is not protected by this
proposal. Do not expose sensitive events or claim desk authentication until the
implementation is merged and unauthorized access tests pass. Rotation and
session invalidation must be checked against that implementation at acceptance.

See [security](../SECURITY.md) and [runbook](../RUNBOOK.md).
