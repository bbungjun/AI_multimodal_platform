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

- `app/api/*`: HTTP routes for authentication, health, prompts, generations, pipelines, assets,
  and file streaming.
- `app/schemas.py`: API DTOs shared by route responses and tests.
- `app/models.py`: SQLAlchemy models for jobs, assets, prompt enhancements, and
  outbox dispatch events.
- `app/identity_models.py`: G2 User and digest-only Session persistence.
- `app/auth/*`: G3 transactional authentication interface, Google identity
  verification and one-time OAuth flow storage.
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

## Authentication Boundary

`AuthService` exposes login start, callback completion, authentication and
idempotent logout. Google code exchange/signature verification and Redis flow
storage stay behind internal adapters. Automated verification replaces Google
only; it uses real isolated Postgres and Redis for lifecycle and HTTP proofs.

The flow cookie keys a SHA-256 Redis namespace in database 1, separate from the
Celery broker database 0. Compose explicitly disables Redis RDB/AOF persistence
to keep flow material off disk. This also makes broker contents ephemeral;
Redis restart/queue recovery needs separate operational validation, not a
durable-queue claim. State is digested; nonce and PKCE verifier exist only
in the one-time, ten-minute flow record. No provider token reaches SQL. Login
upserts by Google subject and preserves role, status and original signup time.
A User row lock serializes admission, logout and activity touch for that User.
At most five Active Sessions remain; a sixth login evicts the oldest by
`(created_at, id)`. Sessions have seven-day absolute and twelve-hour inactivity
expiry, with conditional activity updates at most once every five minutes.
Same-User requests serialize even when no touch is due: this favors correctness
over maximum throughput and requires measurement before a high-traffic rollout.

HTTP exposes `/api/auth/google/start`, `/api/auth/google/callback`,
`/api/auth/me`, and `/api/auth/logout`. Host-only HttpOnly/Lax cookies are Secure
by default. Unsafe cookie requests require an exact trusted Origin. Callback
query data is removed from Uvicorn/httpx access logs; responses are no-store and
no-referrer. The callback redirects to a validated local return path.

Missing Google configuration disables login only. Existing generation routes
are deliberately unchanged and still unauthenticated until G4. G3.1 consumes
the browser-flow, `/me` and logout contracts; G4 consumes
`app.api.auth_dependencies.require_user`. Browser login, ownership and live
OAuth are not delivered by G3. See the [G3 specification](initiatives/g3-auth-session-lifecycle-spec.md)
and [verification record](portfolio/issue-98-auth-session-lifecycle.md).

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
- authenticated workspace UX and ownership enforcement on top of G3
