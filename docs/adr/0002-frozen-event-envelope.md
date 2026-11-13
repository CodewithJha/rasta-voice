# ADR 0002: Frozen event with envelope extensions

Status: Accepted. Date: 13 November 2026.

## Context

Python, browser code and stored events need one stable intent/action shape.
Operational metadata must not silently change that shared event contract.

## Decision

Keep RiderEvent synchronized across the JSON schema, Python model and TypeScript
interface. Put id, created_at, provider metadata and future lifecycle/version
fields in the surrounding record. Simulation adds an outer audio envelope.
Schema/client/workflow changes go in a separate contract PR agreed by both owners.

## Consequences

Features cannot invent extra RiderEvent fields. Consumers must unwrap each
route's actual response shape. The contract check guards mirrored event fields;
it does not certify a future envelope extension automatically.

See [architecture](../ARCHITECTURE.md) and [root workflow](../../CONTRIBUTING.md).
