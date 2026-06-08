# CreativeOps Studio Architecture

CreativeOps Studio is a personal AI creative workspace with an operations-grade
job backend. The app generates images and videos with Vertex AI while keeping
job state, assets, retries, and provider readiness observable from the product.

## System Shape

```text
React/Vite frontend
  -> FastAPI backend
    -> PostgreSQL job, asset, prompt, and pipeline records
    -> Internal asyncio job runner
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
  parent/child relationships.
- `app/state_machine.py`: the only supported path for job state transitions.
- `app/services/jobs/*`: in-process job runner, handlers, and pipeline linking.
- `app/services/vertex/*`: provider boundary for credentials, Imagen, Veo,
  retry/rate-limit helpers, storage, and public error mapping.
- `app/services/llm/enhancer.py`: Gemini-backed prompt enhancement with a mock
  provider fallback.

## Frontend Layers

- `frontend/src/api/*`: API client, DTO types, and compile-time contract checks.
- `frontend/src/hooks/*`: query hooks for jobs, assets, and pipelines.
- `frontend/src/pages/*`: generation, history, job detail, and pipeline views.
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

Generation is job-centric. The API creates durable jobs in Postgres, and an
internal runner claims pending work with row locks. Handlers perform provider
calls, persist generated assets, and transition jobs through the state machine.

Pipelines are modeled as parent/child jobs. A text-to-image parent can unblock
an image-to-video child once an image asset exists.

Failed-job retries are also modeled as jobs. `retry_of_job_id` links the new
pending retry job to the failed source while keeping the original failure record
immutable.

## Storage Model

Asset metadata lives in Postgres. Binary media is stored under `DATA_DIR` and
served through `/files/...` after path containment checks. This keeps local
development simple while preserving a clear future path toward object storage.

## Production Direction

For a personal production app, the next architecture improvements are:

- explicit local/mock/vertex environment profiles
- real-provider cost guardrails
- stronger job observability
- graceful runner shutdown and polling resume visibility
- first-class frontend Ops Console
- optional authentication for a private personal deployment
