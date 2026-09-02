# Local Mock Runbook

Use this runbook for no-cost local development and smoke checks.

## Goal

Run the full app stack without calling paid AI providers.

## Environment

Set mock mode in `.env`:

```env
AI_PROVIDER=mock
APP_ENV=local
POSTGRES_USER=app
POSTGRES_PASSWORD=changeme
POSTGRES_DB=multimodal
GCP_PROJECT_ID=
GCP_LOCATION=us-central1
ENHANCE_MODEL=gemini-2.5-flash
DATA_DIR=/data/assets
JOB_RUNNER_CONCURRENCY=10
JOB_RUNNER_AUTO_START=false
JOB_DISPATCH_MODE=celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_DEFAULT_QUEUE=generation
RATE_LIMIT_IMAGEN_PER_MIN=5
RATE_LIMIT_VEO_PER_MIN=1
RATE_LIMIT_GEMINI_PER_MIN=10
PROVIDER_RETRY_MAX_ATTEMPTS=3
PROVIDER_RETRY_BASE_DELAY_SEC=1.0
PROVIDER_RETRY_MAX_DELAY_SEC=20.0
CELERY_WORKER_CONCURRENCY=2
CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC=5
CELERY_WORKER_SHUTDOWN_GRACE_SEC=60
CELERY_TASK_ACKS_LATE=true
CELERY_TASK_REJECT_ON_WORKER_LOST=true
CELERY_WORKER_PREFETCH_MULTIPLIER=1
OUTBOX_DISPATCHER_BATCH_SIZE=50
OUTBOX_DISPATCHER_POLL_INTERVAL_SEC=1.0
OUTBOX_DISPATCHER_MAX_ATTEMPTS=10
VITE_API_BASE=
VITE_API_PROXY_TARGET=http://backend:8000
VITE_ALLOWED_HOSTS=localhost,127.0.0.1
```

Mock mode should not require live Google credentials.

## Start

```powershell
docker compose config
docker compose up -d --build
docker compose ps
```

Expected services:

- `db` healthy
- `migrate` exits successfully after `alembic upgrade head`
- `redis` healthy and used only as the Celery broker
- `backend` on `http://127.0.0.1:8000`
- `dispatcher` running `python -m app.services.jobs.outbox_dispatcher`
- `worker` healthy, running the Celery `generation` queue with the same database and asset volume
- `frontend` on `http://127.0.0.1:5173`

Postgres remains the source of truth for user-visible job state. Redis/Celery is
only the execution dispatch layer; Celery result state is not used by the API.
The API records job dispatch intent in the Postgres outbox first, then the
dispatcher publishes job ids to Celery.

The default worker has an internal Celery ping healthcheck, a stable
`worker@%h` hostname, explicit `SIGTERM` stop handling, and a configurable
Compose grace period through `CELERY_WORKER_SHUTDOWN_GRACE_SEC`.
Before Celery starts, its fixed command runs `python -m app.schema_control
check`; an incompatible revision exits before work is consumed.

## Schema Migration and Readiness

Inspect the packaged and database revisions without printing the database URL:

```powershell
docker compose run --rm migrate python -m alembic heads
docker compose run --rm migrate python -m alembic current
docker compose run --rm migrate python -m app.schema_control check
```

Normal `docker compose up` runs the finite migration first. Backend, worker,
and dispatcher require its successful completion and also perform their own
read-only check. Do not use application startup as a migration command.

For an isolated upgrade/downgrade/re-upgrade proof, use:

```powershell
python scripts/verify_schema_migrations.py --env-file .env.example
```

The verifier owns and removes only its generated `g1-schema-*` project. Never
substitute the default project or an existing volume.

## Guarded Local Database Reset

Reset is destructive and intended only for the disposable local/test database.
Always preview first:

```powershell
docker compose run --rm -e APP_ENV=local migrate `
  python -m app.schema_control reset `
  --expected-database multimodal
```

Review the redacted environment, host, port, database, revision, and fixed-table
row counts. Execution additionally requires the exact database name and exact
confirmation:

```powershell
docker compose run --rm -e APP_ENV=local migrate `
  python -m app.schema_control reset `
  --expected-database multimodal `
  --execute `
  --confirm RESET:multimodal
```

The command refuses non-local/test environments, non-allowlisted hosts, URL or
live database-name mismatches, and wrong confirmation. It resets only the
selected database's `public` schema; it does not drop the database, remove
volumes or asset files, or invoke a cloud command. If upgrade fails after the
reset, recover with:

```powershell
docker compose run --rm migrate python -m alembic upgrade head
docker compose run --rm migrate python -m app.schema_control check
```

## Local Quality Gate

Before a handoff, run the mock-only local quality gate from the repository root:

```powershell
python scripts/verify_local.py
```

It validates Compose config with `.env.example`, runs backend tests with
`AI_PROVIDER=mock`, and runs frontend lint and build. Use `--env-file` for a
non-secret mock env file; the script refuses `.env`.

The script does not read the repository root `.env`. It also refuses to run
backend tests if `backend/.env` exists, because backend pytest can load that file
implicitly through application settings.

## Health

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
Invoke-RestMethod -Uri "http://127.0.0.1:5173/api/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ops/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/ops/metrics"
```

Expected provider status in mock mode:

```json
{
  "ready": true,
  "status": "mock_provider",
  "credentials": "not_required"
}
```

Expected ops status in mock mode:

- `db: "up"`
- `dispatch.mode: "celery"`
- job counts grouped under `jobs.by_state`
- outbox counts grouped under `outbox.by_status`
- resumable Veo polling count under `jobs.resumable_polling`
- runtime request metrics under `runtime.http`
- provider failure counts under `runtime.provider_failures`

`/api/ops/metrics` returns the same runtime-only metrics without querying the
database. Use it before and after k6 or smoke runs to inspect:

- `http.requests_total`
- `http.errors_total` and `http.error_rate`
- per-endpoint `status_counts`
- per-endpoint `latency_ms.avg_ms`, `p50_ms`, `p95_ms`, and `max_ms`
- `provider_failures.by_code` and `provider_failures.by_status`

The frontend exposes the same operational summary at `/ops`.

## Smoke Flow

Create a text-to-image job, wait for completion, and verify that the returned
asset URL streams from `/files/...`. The generated image should be deterministic
mock PNG bytes.

The backend golden-path smoke automates this flow from the repository root:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
```

Use this variant when `db`, `redis`, `backend`, `dispatcher`, and `worker` are
already running:

```powershell
python scripts/smoke_mock_golden_path.py --base-url http://127.0.0.1:8000
```

The smoke intentionally starts `db`, `redis`, `backend`, `dispatcher`, and
`worker` when `--compose` is used.
It refuses `--env-file .env`, requires `AI_PROVIDER=mock` in the selected env
file, checks prompt enhancement, T2I job completion, asset metadata, PNG file
serving, byte-range streaming, and then deletes the generated job unless
`--keep-job` is passed.

The retry smoke covers the failure and retry workflow, including the frontend
SPA history and job-detail routes:

```powershell
python scripts/smoke_mock_retry_flow.py --compose --env-file .env.example --timeout-sec 90
```

Use this variant when the full stack is already running:

```powershell
python scripts/smoke_mock_retry_flow.py --base-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:5173 --timeout-sec 90
```

It creates a T2I job with the `[[mock-fail:imagen]]` sentinel, waits for the
source job to fail with no assets and `vertex_charged: false`, calls
`POST /api/generations/{source_id}/retry`, checks the retry job contract, verifies
`/jobs/{retry_id}` returns a non-empty SPA response, and deletes the retry job
before the source job unless `--keep-jobs` is passed.

## Pending Job Repair

If the outbox dispatcher cannot publish to Redis/Celery, the outbox event stays
`pending` until a later dispatcher attempt. When the max attempt limit is
reached, the event is marked `failed` while the job remains `pending` and
unmodified.

As a last-resort operator repair, directly reenqueue pending unblocked jobs from
the repository root with process environment variables already set:

```powershell
python scripts/reenqueue_pending_jobs.py --limit 100
```

The repair command bypasses the outbox and sends only job ids through the same
Celery dispatch adapter. Duplicate dispatch is tolerated because Celery tasks
claim only pending jobs before executing. The command refuses to run while
`.env` files are present in the repository root, backend directory, or current
working directory. It prints only selected/dispatched/failed counts, not
prompts, parameters, credentials, or asset paths.

## Veo Polling Resume

Veo video tasks can sit in `polling` while waiting for a Vertex operation. The
Celery worker uses late acknowledgements, `reject_on_worker_lost`, and prefetch
`1` so a worker restart can redeliver the task. Redelivered tasks resume only
`t2v`/`i2v` jobs that are still `polling` and have a
`vertex_operation_name`; the handler polls the saved operation name instead of
submitting a new video request.

If an older task was lost before these settings were active, reenqueue
resumable polling jobs from the repository root with process environment
variables already set:

```powershell
python scripts/reenqueue_polling_jobs.py --limit 100
```

The polling repair command uses the same `.env` refusal and count-only output
rules as pending job repair.

The legacy polling worker remains available as a manual fallback:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m app.worker
```

Do not run the polling worker and the default dispatcher/Celery worker against
the same local stack unless intentionally performing a controlled repair run.

Backend tests may use the exact prompt sentinel `[[mock-fail:imagen]]` to force a
deterministic Imagen mock provider failure. Treat it as a test-only failure-path
trigger for job error contracts, not as part of manual smoke or normal studio
usage.

In mock mode, a completed job may report `vertex_charged: true`; this only means
the mock provider handler finished its generation step. It is not real Vertex
billing and does not prove any external AI call happened.

Do not use this backend smoke to judge AI output quality or frontend preview
behavior. It verifies the backend HTTP flow: API, worker runner, database,
storage, and file streaming.

## Stop

```powershell
docker compose down
```

Use `down -v` only when intentionally removing local database and asset volumes.
