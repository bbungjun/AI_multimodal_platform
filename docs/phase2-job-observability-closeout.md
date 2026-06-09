# Phase 2 Job Observability Closeout

## Summary

This step improved dispatch and worker observability without changing API
response contracts or mutating job state for non-state events.

Implemented:

- `DispatchResult` now includes:
  - `queue`
  - `task_id`
  - `error_code`
- dispatch boundaries emit structured log fields for job id, reason, mode,
  queue, task id, status, and error code.
- `RepairResult` now preserves individual dispatch results in addition to
  selected/dispatched/failed counts.
- `ProcessJobResult` now includes:
  - `previous_state`
  - `claimed_state`
  - handler execution flag
- Celery task claim/no-op boundaries emit structured log fields.

## Policy

`Job.state_history` remains reserved for state transitions only. Dispatch
attempts, repair attempts, Celery task IDs, and duplicate/no-op decisions are
observability events, not job state transitions.

That means:

- `pending -> queued` claim remains in `state_history`.
- dispatch success/failure is logged and returned as `DispatchResult`.
- pending repair results are returned as `RepairResult`.
- duplicate, terminal, blocked, missing, and invalid task decisions are logged
  and returned as `ProcessJobResult`.

## Verification

All verification used `AI_PROVIDER=mock`.

Passed:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_enqueue.py tests/test_reenqueue_pending.py tests/test_celery_tasks.py -q
```

Result: `16 passed`

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_generation_api.py tests/test_pipeline_api.py tests/test_job_handlers.py -q
```

Result: `77 passed`
