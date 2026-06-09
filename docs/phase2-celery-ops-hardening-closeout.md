# Phase 2 Celery Ops Hardening Closeout

## Summary

This step tightened Celery worker operations after the initial Phase 2 dispatch
layer.

Implemented:

- Celery-specific worker settings:
  - `CELERY_DEFAULT_QUEUE`
  - `CELERY_WORKER_CONCURRENCY`
  - `CELERY_WORKER_HEALTHCHECK_TIMEOUT_SEC`
  - `CELERY_WORKER_SHUTDOWN_GRACE_SEC`
- Worker command now uses a stable `worker@%h` hostname.
- Worker command uses Celery-specific queue and concurrency env instead of the
  legacy polling runner concurrency name.
- Docker Compose worker healthcheck uses `celery inspect ping` against the
  worker's own hostname.
- Docker Compose worker shutdown now explicitly uses `SIGTERM` and configurable
  grace period.
- Local mock/testing docs now describe the worker health and shutdown behavior.

## Verification

All verification used `AI_PROVIDER=mock` and `.env.example`.

Passed:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_celery_app.py tests/test_compose_worker_service.py -q
```

Result: `10 passed`

```powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --services
docker compose --env-file .env.example up -d --build db redis backend worker
docker compose --env-file .env.example ps
```

Result: services included `db`, `redis`, `backend`, `worker`; worker reported
`healthy`.

```powershell
python scripts/smoke_mock_golden_path.py --base-url http://127.0.0.1:8000 --timeout-sec 120
```

Result: `SMOKE PASSED`
