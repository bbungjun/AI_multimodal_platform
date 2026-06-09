# Phase 1 Worker Process Separation Closeout

## Status

Phase 1 is complete as of commit `a88cba9 feat: split api and worker processes`.

The API process and job execution process are now separated in local mock
Compose. FastAPI no longer starts the job runner by default. A standalone
worker process runs the existing `InProcessJobRunner` and continues to use
Postgres as the job source of truth.

No Redis, Celery, outbox table, queue routing, or broker dependency was added in
this phase.

## What Changed

- `backend/app/config.py`
  - Added `JOB_RUNNER_AUTO_START`, defaulting to `false`.
- `backend/app/main.py`
  - FastAPI lifespan still initializes `DATA_DIR` and database schema.
  - Job runner startup is gated by `JOB_RUNNER_AUTO_START`.
- `backend/app/worker.py`
  - Added standalone worker bootstrap for `python -m app.worker`.
  - Worker creates `DATA_DIR`, validates provider mode, initializes schema,
    runs `InProcessJobRunner`, and closes DB connections.
  - `SIGTERM` and `SIGINT` cancel the worker task so runner shutdown and DB
    cleanup can run.
- `docker-compose.yml`
  - Added a `worker` service using the backend image, shared database env, and
    shared asset volume.
  - Added `stop_grace_period: 45s` for worker drain.
- `docker-compose.vertex.yml`
  - Mounts configured credential file into both `backend` and `worker`.
- Mock smoke scripts
  - `--compose` now starts `worker` with the backend stack.
- README and docs
  - Updated architecture, lifecycle, testing, and runbooks to describe API and
    worker as separate processes.

## Architecture After Phase 1

```text
React/Vite frontend
  -> FastAPI API process
    -> Postgres job/status records
    -> /api and /files serving

Worker process
  -> InProcessJobRunner
    -> Postgres pending job polling and row-lock claim
    -> state_machine.transition(...)
    -> provider/storage boundary
```

Postgres remains the authoritative store for job state, payload, prompt
enhancement links, pipeline relationships, and asset metadata. The worker does
not trust any external queue message because no external queue exists yet.

## Gates Verified

- API process does not auto-start the runner by default.
- Worker process runs `InProcessJobRunner` independently.
- Worker bootstrap covers `DATA_DIR`, schema init, runner execution, shutdown,
  and DB close.
- Worker provider guard allows `AI_PROVIDER=mock` and rejects silent fallback to
  implicit `vertex`.
- API and worker share `DATABASE_URL`, `DATA_DIR`, `AI_PROVIDER`, concurrency
  config, and the `assets:/data/assets` volume in Compose.
- Worker handles `SIGTERM`/`SIGINT` by cancelling the running worker task.
- Smoke scripts no longer assume backend-only runner execution.
- Redis/Celery/outbox/queue routing did not enter the codebase.

## Verification Evidence

All verification used `AI_PROVIDER=mock` or deterministic fake providers. No
real Vertex, Gemini, Imagen, or Veo calls were performed.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Result: `235 passed`.

```powershell
cd frontend
npm run lint
npm run build
```

Result: both passed.

```powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --services
```

Result: config passed; services were `db`, `backend`, `frontend`, `worker`.

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
python scripts/smoke_mock_retry_flow.py --compose --env-file .env.example --timeout-sec 90
```

Result: both smoke checks passed.

```powershell
python scripts/verify_local.py
```

Result: `VERIFY PASSED`.

## Residual Risks

- API and worker both call `init_db_schema()`. This is acceptable for current
  local mock Compose and tests, but production migration should eventually move
  schema management into explicit migrations.
- `SIGTERM` handling is unit-tested and Compose gives the worker a longer grace
  period than the runner shutdown timeout. A real active long-running provider
  drain test is still future work.
- If an operator explicitly enables `JOB_RUNNER_AUTO_START=true` while also
  running the worker service, duplicate runner processes can exist. The default
  local Compose path keeps it disabled.

## Phase 2 Handoff

Phase 2 can focus on Redis/Celery without also solving process separation.

The next work should introduce Redis strictly as Celery's broker and keep
Postgres as the source of truth. Celery task payloads should carry `job_id`
only, and tasks should re-read the latest job record from Postgres before doing
provider or storage work.
