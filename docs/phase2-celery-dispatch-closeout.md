# Phase 2 Celery Dispatch Closeout

## Summary

Phase 2 introduced Redis/Celery as the local mock dispatch layer while keeping
Postgres as the user-visible job source of truth.

Implemented:

- `JOB_DISPATCH_MODE=celery` and `CELERY_BROKER_URL` local config.
- Celery app boundary with JSON serialization, single `generation` queue, and
  ignored task results.
- `job_id`-only enqueue adapter.
- API dispatch after committed generation, retry, and pipeline parent jobs.
- Celery task claim guard:
  - invalid UUID no-op
  - missing job no-op
  - terminal job no-op
  - blocked job no-op
  - non-pending duplicate task no-op
  - pending unblocked job transitions to `queued` with `runner: celery`
- Pipeline child dispatch after parent T2I completion unblocks the child.
- Pending unblocked job repair service and CLI.
- Docker Compose Redis service and default Celery worker.
- Mock smoke scripts updated to start Redis.
- Local mock and testing docs updated.

Not implemented in Phase 2:

- Outbox table.
- Dead-letter queue.
- Provider-specific queue routing.
- Prompt enhancement queueing.
- Celery result backend as job state.
- Live Vertex/Gemini/Imagen/Veo calls.

## Safety Notes

Celery task payloads contain only the job UUID string. Prompts, model
parameters, asset paths, provider settings, and credentials are not sent through
Redis.

The API creates and commits jobs in Postgres first, then dispatches. Dispatch
failure is logged/reported but does not mutate the committed job. A committed
job remains `pending` and can be requeued with:

```powershell
python scripts/reenqueue_pending_jobs.py --limit 100
```

The repair CLI refuses to run while `.env` files are present in the repository
root, backend directory, or current working directory.

The legacy `python -m app.worker` polling worker remains available as a manual
fallback. The default Compose stack runs the Celery worker only, so the polling
worker and Celery worker do not process the same queue concurrently.

## Verification

All verification used `AI_PROVIDER=mock`.

Passed:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py tests/test_enqueue.py tests/test_celery_tasks.py tests/test_reenqueue_pending.py tests/test_compose_worker_service.py tests/test_smoke_mock_golden_path_script.py tests/test_smoke_mock_retry_script.py -q
```

Result: `40 passed`

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py tests/test_job_handlers.py tests/test_pipeline_link.py tests/test_job_runner.py -q
```

Result: `92 passed`

```powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --services
```

Services included: `db`, `redis`, `backend`, `frontend`, `worker`

```powershell
python scripts/smoke_mock_retry_flow.py --compose --env-file .env.example --timeout-sec 120
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 120
```

Result: both `SMOKE PASSED`

```powershell
python scripts/verify_local.py
```

Result: `VERIFY PASSED`, including backend `260 passed`, frontend lint, and
frontend build.

## Debugging Note

During retry smoke, Celery initially failed on the second job because each task
used `asyncio.run(...)` with the same asyncpg connection pool across different
event loops. The fix closes the DB connection pool at the end of each Celery
task entrypoint, preventing loop-bound connection reuse.
