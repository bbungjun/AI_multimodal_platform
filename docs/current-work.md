# Current Work Handoff

This file is the shared handoff point for working on this repository from more
than one machine. Read it after `AGENTS.md` and before making changes. Update it
at the end of every meaningful work session.

## Workspace Rule

- Treat the current checkout directory as the repository root.
- Do not write machine-specific absolute paths into committed docs.
- Use repo-relative paths in docs and commands whenever possible.
- Keep `.env`, credential files, generated media, local Docker volumes,
  virtualenvs, `node_modules`, and runtime logs local to each machine.
- Use `.env.example` as the shared template and each machine's `.env` as local
  state.

## Current Project State

- Repository: `bbungjun/AI_multimodal_platform`
- Default branch: `main`
- Default local mode: `AI_PROVIDER=mock`
- Runtime shape: Docker Compose runs `db`, `redis`, `backend`, `dispatcher`,
  `frontend`, and `worker`.
- Job dispatch shape: API writes jobs and outbox events to Postgres; dispatcher
  publishes `job_id` to Redis/Celery; Celery worker claims jobs from Postgres.
- Source of truth for user-visible job state: Postgres, not Redis or Celery
  result state.
- Portfolio/demo safety defaults: `CELERY_WORKER_CONCURRENCY=2`,
  `RATE_LIMIT_GEMINI_PER_MIN=10`, `RATE_LIMIT_IMAGEN_PER_MIN=5`, and
  `RATE_LIMIT_VEO_PER_MIN=1`.
- Celery video-task recovery defaults: `CELERY_TASK_ACKS_LATE=true`,
  `CELERY_TASK_REJECT_ON_WORKER_LOST=true`, and
  `CELERY_WORKER_PREFETCH_MULTIPLIER=1`.
- Provider retry/backoff defaults: `PROVIDER_RETRY_MAX_ATTEMPTS=3`,
  `PROVIDER_RETRY_BASE_DELAY_SEC=1.0`, and
  `PROVIDER_RETRY_MAX_DELAY_SEC=20.0`.
- Ops visibility: `/api/ops/health` and the frontend `/ops` route expose DB
  backed job counts, outbox counts, resumable polling count, dispatch settings,
  and recent failed jobs.
- Documentation loading policy: read this file first, then load only the
  directly relevant reference doc for the task. Historical phase plans and
  closeout files were removed to keep agent startup fast.

## Machine Setup Notes

For a new laptop or desktop checkout:

```powershell
git pull
.\scripts\setup_local.ps1
```

Run the full local quality gate when dependencies are installed:

```powershell
.\scripts\setup_local.ps1 -RunVerify
```

Adjust `.env` only for local machine needs. In mock mode, leave credential
values empty. In Vertex mode, configure credentials locally and never commit or
paste credential contents.

## Last Completed Work

As of 2026-06-12, the documentation was aligned with the current
Redis/Celery/outbox runtime and the shared multi-machine workflow:

- Updated README architecture and mock-mode env example to include Redis,
  dispatcher, Celery worker, and outbox settings.
- Updated `AGENTS.md` to describe the current Compose services and require this
  handoff file.
- Removed long historical migration docs after their useful current state was
  folded into this handoff file and the canonical reference docs.
- Removed committed machine-specific repository paths from Markdown files.
- Cleaned smoke-run documentation so already-running service lists include
  Redis alongside `db`, `backend`, `dispatcher`, `worker`, and `frontend` where
  applicable.
- Added `scripts/setup_local.ps1` so laptop/desktop checkouts can create a local
  `.env` from `.env.example` without overwriting existing local settings, verify
  Compose config, and optionally run the full quality gate with `-RunVerify`.
- Tightened default portfolio/demo safety settings so Gemini, Imagen, and Veo
  request windows are conservative by default and Celery starts with worker
  concurrency `2`. The values remain configurable through `.env`.
- Started Phase 4B by making provider retry/backoff policy configurable from
  environment settings. Transient provider failures now use the configured
  retry policy before the job is marked failed with public error metadata.
- Completed Phase 4C Veo polling resume support. Long-running Celery tasks now
  use late ack/reject-on-worker-lost/prefetch `1`, redelivered `t2v`/`i2v`
  polling jobs resume from the saved `vertex_operation_name`, and
  `scripts/reenqueue_polling_jobs.py` can reenqueue stranded polling jobs.
- Added Phase 4D dead-letter/repair metadata for retry-exhausted provider
  failures. Failed jobs now keep `dead_letter`, `dead_letter_reason`, and
  `repair_action` in `job.error`, and the detail/history UI surfaces repair
  status plus repair-oriented retry copy.
- Hardened I2V duplicate protection with source asset row locking, a Postgres
  partial unique index for active I2V jobs, and conflict mapping for commit-time
  uniqueness races.
- Completed Phase 4E minimal worker/queue health metrics. The backend exposes
  `/api/ops/health`, the frontend has an `/ops` route, and tests cover job
  state counts, outbox status counts, resumable polling counts, dispatch
  recovery settings, and recent failed job summaries.
- Pruned completed Phase 1-3 implementation plans and closeout documents so
  agents no longer spend time reading stale migration history.

## Next Suggested Work

- Use `scripts/setup_local.ps1` after switching machines or after a fresh clone.
  Pass `-RunVerify` when local Python/Node dependencies are installed and you
  want the full quality gate. Pass `-Force` only when intentionally regenerating
  `.env` from `.env.example`.
- If an older local `.env` already exists, make sure it includes the current
  rate-limit keys, provider retry keys, `CELERY_WORKER_CONCURRENCY=2`,
  `CELERY_TASK_ACKS_LATE=true`, `CELERY_TASK_REJECT_ON_WORKER_LOST=true`, and
  `CELERY_WORKER_PREFETCH_MULTIPLIER=1`; `setup_local.ps1` does not overwrite
  existing local `.env` files unless `-Force` is used.
- Phase 5 recommendation: create a concise AWS deployment runbook covering API,
  worker, dispatcher, Postgres, Redis, asset storage, secrets, and how to use
  `/ops` after deployment.
- Run the full local quality gate before committing documentation changes:

```powershell
python scripts/verify_local.py
```

## Verification Log

Latest Ops metrics checks:

```powershell
git diff --check
cd backend; $env:AI_PROVIDER='mock'; python -m pytest tests/test_ops_metrics.py tests/test_ops_api.py tests/test_health.py tests/test_celery_app.py tests/test_reenqueue_pending.py -q
cd frontend; npm run lint
cd frontend; npm run build
python scripts/verify_local.py
```

Expected:

- no whitespace errors
- related backend regression tests pass
- frontend typecheck and production build pass
- full local quality gate passes
- only intentional working-tree changes are present
