# ADR 0003: Local Asset Storage

## Status

Accepted for local and personal deployments.

## Decision

Generated media bytes are stored under `DATA_DIR`. Asset metadata is stored in
Postgres and media is served through the backend.

## Rationale

Local asset storage keeps the app easy to run with Docker Compose. It also makes
mock-mode tests and frontend previews straightforward.

## Consequences

Benefits:

- simple local development
- no object-storage dependency
- direct file streaming and byte-range support
- clear storage safety tests

Trade-offs:

- no built-in backup or retention policy
- local volume management is required
- scaling beyond one host needs a storage adapter

## Follow-Up

Add retention, checksums, and an object-storage abstraction when the app needs
remote deployment or durable media archives.
