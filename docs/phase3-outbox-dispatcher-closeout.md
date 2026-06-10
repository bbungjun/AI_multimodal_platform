# Phase 3 Outbox Dispatcher Closeout

## Summary

This step added a transactional outbox between API job creation and Celery
dispatch. The goal is to remove the gap where the API commits a job but fails
before publishing it to Redis/Celery.

Implemented:

- `OutboxEvent` model with pending/published/failed status, attempt count,
  `last_error`, and `published_at`.
- `add_job_dispatch_event(...)` helper that stores only `job_id` and dispatch
  reason in the outbox payload.
- generation create/retry APIs now write a job and outbox event in the same DB
  transaction.
- pipeline parent creation writes a parent dispatch event in the same DB
  transaction.
- pipeline child unblock writes a child dispatch event before committing the
  unblock.
- `outbox_dispatcher` process reads pending outbox events with row locks,
  publishes job ids through the existing dispatch adapter, and records
  published/failed/pending retry state.
- Docker Compose now includes a dedicated `dispatcher` service.
- mock smoke scripts now start `dispatcher` when `--compose` is used.

## Runtime Shape

```text
FastAPI API
  -> Postgres jobs + outbox event
Outbox dispatcher
  -> Redis/Celery job id dispatch
Celery worker
  -> Postgres job claim
  -> provider handler
```

The API, dispatcher, and worker still keep Postgres as the source of truth. Redis
does not store user-visible job state, prompts, parameters, credentials, or
asset paths.

## Verification

All verification used `AI_PROVIDER=mock`.

Passed:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

Result: `271 passed`

```powershell
python scripts\verify_local.py
```

Result: `VERIFY PASSED`
