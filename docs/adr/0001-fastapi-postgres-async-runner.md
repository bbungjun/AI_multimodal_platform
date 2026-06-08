# ADR 0001: FastAPI, Postgres, And An Internal Async Runner

## Status

Accepted.

## Decision

CreativeOps Studio stores generation jobs in Postgres and processes them with an
internal asyncio runner started by the FastAPI app.

## Rationale

This keeps the personal deployment small while preserving durable job state.
Postgres row locks allow workers to claim pending jobs without adding Redis or
Celery. FastAPI and async SQLAlchemy are already part of the backend stack.

## Consequences

Benefits:

- fewer moving parts for local and personal deployments
- durable job history in the same database as app metadata
- easy mock-mode test coverage
- clear route from API request to job lifecycle

Trade-offs:

- multi-replica deployment needs additional coordination
- long-running Veo polling must be resumable after restarts
- graceful shutdown and stuck-job observability matter more

## Follow-Up

Add structured job events, metrics, and explicit runner lifecycle controls
before treating the app as a multi-instance production service.
