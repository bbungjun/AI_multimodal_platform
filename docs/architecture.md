# CreativeOps Studio Architecture

CreativeOps Studio is a personal AI creative workspace with an operations-grade
job backend. The app generates images and videos with Vertex AI while keeping
job state, assets, retries, and provider readiness observable from the product.

## System Shape

```text
React/Vite frontend
  -> FastAPI backend
    -> PostgreSQL job, asset, prompt, pipeline, and outbox records
    -> Local DATA_DIR file streaming
Outbox dispatcher process
  -> publishes job ids from Postgres outbox to Redis/Celery
Celery worker process
  -> claims pending jobs from Postgres
  -> Local DATA_DIR asset storage
  -> Vertex AI through google-genai
```

The backend owns all provider calls. The frontend never talks to Vertex AI
directly and does not need provider credentials.

## Backend Layers

- `app/api/*`: HTTP routes for health, prompts, generations, pipelines, assets,
  and file streaming.
- `app/schemas.py`: API DTOs shared by route responses and tests.
- `app/models.py`: SQLAlchemy models for jobs, assets, prompt enhancements, and
  outbox dispatch events.
- `app/state_machine.py`: the only supported path for job state transitions.
- `app/celery_app.py`: Celery app configuration for Redis-backed job dispatch.
- `app/worker.py`: legacy standalone polling worker bootstrap for manual fallback.
- `app/services/jobs/*`: Celery task wrapper, outbox dispatcher, dispatch
  adapter, repair helper, handlers, and pipeline linking.
- `app/services/ops/*`: DB-backed operational metrics for job state, outbox,
  resumable polling, and recent failure visibility.
- `app/services/vertex/*`: provider boundary for credentials, Imagen, Veo,
  retry/rate-limit helpers, storage, and public error mapping.
- `app/services/llm/enhancer.py`: Gemini-backed prompt enhancement with a mock
  provider fallback.

## Frontend Layers

- `frontend/src/api/*`: API client, DTO types, and compile-time contract checks.
- `frontend/src/hooks/*`: query hooks for jobs, assets, and pipelines.
- `frontend/src/pages/*`: generation, history, job detail, pipeline, and ops
  views.
- `frontend/src/components/*`: reusable UI and icon components.

The next production pass should organize these pages into a clearer product
information architecture: Generate Studio, Asset Library, Job Timeline, and Ops
Console.

## Provider Boundary

The provider boundary is intentionally narrow. `AI_PROVIDER=mock` returns
deterministic media and prompt data without credentials. `AI_PROVIDER=vertex`
uses `google-genai` with `genai.Client(vertexai=True, ...)`. Automated tests use
mock or fake providers and must not call paid AI services.

## Job Model

Generation is job-centric. The API creates durable jobs in Postgres and writes a
minimal outbox event in the same transaction. The outbox dispatcher publishes
only the job id and dispatch reason to Celery. The Celery worker then claims the
pending job with a row lock before running handlers. Handlers perform provider
calls, persist generated assets, and transition jobs through the state machine.

Pipelines are modeled as parent/child jobs. A text-to-image parent can unblock
an image-to-video child once an image asset exists.

Failed-job retries are also modeled as jobs. `retry_of_job_id` links the new
pending retry job to the failed source while keeping the original failure record
immutable.

The Ops view reads `/api/ops/health`, which derives operational status from
Postgres rather than Celery result state. It reports job state counts, outbox
status counts, resumable Veo polling jobs, worker dispatch settings, and recent
failed job summaries for deployment triage.

## Storage Model

Asset metadata lives in Postgres. Binary media is stored under `DATA_DIR` and
served through `/files/...` after path containment checks. This keeps local
development simple while preserving a clear future path toward object storage.

## Production Direction

For a personal production app, the next architecture improvements are:

- explicit local/mock/vertex environment profiles
- real-provider cost guardrails
- AWS deployment runbook and environment profile
- object storage choice for generated media
- optional authentication for a private personal deployment
