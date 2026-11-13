# ADR 0004: Shared desk passcode instead of a user database

Status: Accepted for the merged issue 20 implementation. Updated: 13 November 2026.

## Context

The two-person demo needs desk access control without account signup, password
recovery or a user database. Desk reads and database exports are now protected;
rider speech controls remain public and budget-limited.

## Decision

Keep DISPATCH_PASSCODE server-side. Desk reads accept a signed session cookie
or the X-Dispatch-Passcode header, using timing-safe verification. Unlock failure
limits default to five attempts in 600 seconds. Cookie-authenticated protected
writes require a CSRF token. Cookies are HttpOnly for the session, SameSite=Lax,
and Secure on HTTPS. Production startup requires the configured secret.

## Consequences

A shared secret cannot identify individual people. Cookie actors are synthetic
session tokens, not verified identities. Rotation affects every desk: replace
the host secret and restart, then test old-cookie rejection and a fresh unlock.
A missing development passcode fails desk routes closed with 503. Public HTTPS,
proxy behavior and future security-header hardening need their own checks;
this ADR does not claim issue 27 or per-user authorization is complete.

See [security](../SECURITY.md), [runbook](../RUNBOOK.md) and
[passcode rotation](../DEPLOY.md#passcode-rotation).
