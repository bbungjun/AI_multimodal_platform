# ADR 0006: Mock Provider For Cost-Free Development

## Status

Accepted.

## Decision

The app includes a deterministic mock provider selected by `AI_PROVIDER=mock`.

## Rationale

Gemini, Imagen, and Veo can create real cost. Development and automated tests
need to verify API flow, job handling, storage, and frontend previews without
external provider calls.

## Consequences

Benefits:

- no-cost automated tests
- credential-free local development
- deterministic media bytes for preview and storage checks
- strong guard against accidental provider calls in tests

Trade-offs:

- mock mode does not validate AI quality
- live provider QA remains a manual, cost-aware process

## Follow-Up

Keep mock outputs realistic enough for product flow validation, but do not blur
the boundary between deterministic app tests and live AI quality checks.
