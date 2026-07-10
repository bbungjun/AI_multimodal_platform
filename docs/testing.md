# Testing Strategy

Tests should prove the app flow without making real AI calls.

## Default Test Mode

Use `AI_PROVIDER=mock` or fake provider clients for automated tests. Tests must
not call Vertex AI, Gemini, Imagen, or Veo directly.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest
```

## Local Quality Gate

Run the local quality gate from the repository root before handing off a change:

```powershell
python scripts/verify_local.py
```

By default, the script uses `.env.example` and runs:

- `docker compose --env-file .env.example config --quiet`
- backend `python -m pytest` with `AI_PROVIDER=mock`
- frontend `npm run lint`
- frontend `npm run build`

The script refuses `--env-file .env`, validates that the selected env file
exists, and does not print env file values. For focused checks, use
`--skip-compose`, `--skip-backend`, or `--skip-frontend`.

The quality gate does not read the repository root `.env`. Because backend
settings can implicitly load `backend/.env` during pytest, the script refuses to
run backend tests when `backend/.env` exists. Use `--skip-backend` only for
compose/frontend-focused checks.

## GitHub Actions CI

The default CI workflow runs on pull requests, pushes to `main`, and manual
dispatch. It uses Python 3.11, Node 20, `AI_PROVIDER=mock`, installs backend and
frontend dependencies, then runs `python scripts/verify_local.py` from the
repository root. CI must stay mock-only and must not require provider
credentials.

Compose smoke up/down is intentionally not part of the default CI path. Keep
those checks local/manual for now, or consider a separate future
`workflow_dispatch` or nightly workflow if the added runtime cost becomes worth
it.

For manual golden-path validation, `.github/workflows/smoke-mock-golden-path.yml`
is available through `workflow_dispatch` only. It runs the mock backend HTTP
smoke with Compose and is intentionally not part of the default PR/push CI path.

## Coverage Anchors

Important backend contracts are already protected by focused tests:

- health readiness and mock-provider readiness
- ops metrics API for job state, outbox status, resumable polling, dispatch
  settings, and recent failure summaries
- runtime observability for HTTP throughput, error rate, latency samples, and
  provider failure code counts
- Prometheus exposition parsing for API route/status counters, request duration
  histograms, and provider failure labels
- GKE Managed Service for Prometheus scrape wiring and opt-in Cloud Monitoring
  alert-policy safety defaults
- state machine transitions and terminal behavior
- storage path safety, file roundtrips, and range streaming
- job runner row locking, concurrency, orphan sweep, and polling resume
- outbox event payload hygiene, dispatcher retry/failure handling, Celery
  dispatch config, `job_id`-only enqueue, task idempotency, pending job repair,
  and Veo polling reenqueue repair
- Celery worker Compose healthcheck, explicit queue/concurrency env, and
  long-running task redelivery settings
- dispatch/repair/task observability fields without mutating job state history
- job handlers for T2I, T2V, I2V, and pipeline linking
- prompt enhancement parsing, validation, provider retry/backoff, invalid
  response repair retry, language mismatch rejection after one retry, and
  configured model selection and metrics recording
- zero-valued provider-failure Prometheus series before the first live failure,
  so alert policies can be provisioned before an incident
- cumulative request-duration histogram buckets used for dashboard p95 latency
- opt-in Cloud Monitoring custom service, 99.5%/28-day availability SLO, and
  reliability dashboard wiring, including compliance, error-budget, and
  one-hour burn-rate selectors
- pinned hosted image security workflow, fixable HIGH/CRITICAL vulnerability
  gate, SPDX SBOM generation, and verified Cloud Build provenance configs
- digest-only personal GCP release profile, Terraform deployment change
  allowlist, rollout/health verification, and previous-digest automatic
  rollback path
- Vertex adapter parsing and public error mapping with fake clients
- generation, pipeline, asset, and delete API contracts
- failed-generation retry API contracts, including I2V source asset validation
- model relationship behavior and cascade/detach rules

These tests are the safety net for repository detox and productionization.

The mock Imagen provider also has a test-only failure sentinel:
`[[mock-fail:imagen]]`. In `AI_PROVIDER=mock`, and only when no explicit client is
passed, this prompt fragment raises a deterministic non-retryable provider error
without constructing a Vertex client. Use it in automated tests to verify failed
job error serialization, no-asset writes, `vertex_charged: false`, single-attempt
failure, and pipeline child cascade behavior.

## Frontend Checks

Frontend verification should keep:

```powershell
cd frontend
npm ci
npm run lint
npm run build
```

Future work should add stronger UI tests around:

- Generate Studio request flow
- Asset Library previews
- Job Timeline state display
- Ops Console health and error states
- backend error code rendering

## Compose Checks

Docker Compose config should be checked before starting the stack:

```powershell
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example config --services
```

For no-cost local smoke checks, use mock mode. For live Vertex QA, follow the
manual runbook and expect provider cost risk.

Expected local mock services include `db`, `redis`, `backend`, `dispatcher`,
`worker`, and `frontend`. The `dispatcher` publishes Postgres outbox events to
Redis/Celery. The default `worker` is a Celery worker and should report healthy
after its internal Celery ping succeeds. The legacy `python -m app.worker`
polling runner is retained only as a manual fallback and should not run
concurrently with the default dispatcher and Celery worker in normal local
smoke.

## Job Observability

Job `state_history` is reserved for state transitions only. Dispatch attempts,
Celery task IDs, queue names, outbox attempts, repair counts, and
duplicate/no-op task reasons must not be appended to `state_history` unless a
real job state transition occurs.

For Phase 2 local operations, observability lives in:

- `DispatchResult`: job id, reason, mode, queue, Celery task id, enqueue status,
  and error code
- `OutboxBatchResult`: selected/published/failed/pending counts plus
  per-event result records
- `RepairResult`: selected/dispatched/failed counts plus individual
  `DispatchResult` records
- polling repair uses the same `RepairResult` shape for resumable `t2v`/`i2v`
  jobs with saved Vertex operation names
- `ProcessJobResult`: claim/no-op reason, previous state, claimed state, and
  whether the handler executed
- structured log fields emitted by dispatch and task claim boundaries
- `OpsHealthResponse`: DB-backed job/outbox/polling/dispatch/failure summary
  for deployment triage

This keeps Postgres job state clean while still making dispatch failures and
worker no-op decisions diagnosable.

## Backend HTTP Smoke

Use the mock-only golden-path smoke to verify the backend HTTP contract, worker
runner, database persistence, local asset storage, and byte-range file
streaming without calling Vertex AI, Gemini, Imagen, or Veo.

From the repository root, start `db`, `redis`, `backend`, `dispatcher`, and
`worker` through Compose and run the smoke:

```powershell
python scripts/smoke_mock_golden_path.py --compose --env-file .env.example --timeout-sec 90
```

If `db`, `redis`, `backend`, `dispatcher`, and `worker` are already running in
mock mode, run the same flow against the backend base URL:

```powershell
python scripts/smoke_mock_golden_path.py --base-url http://127.0.0.1:8000
```

The script refuses `--env-file .env`, parses only plain `KEY=VALUE` names from
the selected env file, requires `AI_PROVIDER=mock`, and passes
`AI_PROVIDER=mock` to `docker compose` when `--compose` is used.

Expected coverage:

- `GET /api/health` reports `ok`, `ready`, DB up, `mock_provider`, and
  credentials `not_required`
- `POST /api/prompts/enhance` creates a mock prompt draft
- `POST /api/generations` creates a T2I Imagen job using the accepted enhanced
  prompt
- `GET /api/generations/{job_id}` reaches `completed` with
  `queued -> generating -> downloading -> completed` history
- `GET /api/assets/{asset_id}` returns matching asset metadata
- `/files/...` returns PNG bytes and supports `Range: bytes=0-7` with HTTP 206
- `DELETE /api/generations/{job_id}` removes the terminal job and local asset

In mock mode, `vertex_charged: true` means the generation handler completed its
provider step. It does not indicate real Vertex billing or external provider
usage.

## I2V Duplicate Guard Smoke

Use the mock-only I2V duplicate guard smoke to verify that repeated or concurrent
image-to-video requests for the same source image create only one active Veo job.

From the repository root, start `db`, `redis`, `backend`, `dispatcher`, and
`worker` through Compose and run:

```powershell
python scripts/smoke_mock_i2v_duplicate_guard.py --compose --env-file .env.example --timeout-sec 90
```

If those services are already running in mock mode, run:

```powershell
python scripts/smoke_mock_i2v_duplicate_guard.py --base-url http://127.0.0.1:8000 --timeout-sec 90
```

Expected coverage:

- a source T2I job completes and returns one image asset
- two near-simultaneous I2V requests use the same `source_asset_id`
- one request returns HTTP 201 with a new I2V job id
- the other request returns HTTP 409 with the duplicate-active-I2V message
- the created I2V job reaches `completed` and can be cleaned up before deleting
  the source T2I job

## Retry HTTP Smoke

Use the mock-only retry smoke to verify the failed-generation retry path across
the backend API, worker runner, frontend SPA routes, and cleanup behavior.

From the repository root, start the full local mock stack through Compose and run
the smoke:

```powershell
python scripts/smoke_mock_retry_flow.py --compose --env-file .env.example --timeout-sec 90
```

If `db`, `redis`, `backend`, `dispatcher`, `worker`, and `frontend` are already
running in mock mode, run:

```powershell
python scripts/smoke_mock_retry_flow.py --base-url http://127.0.0.1:8000 --frontend-url http://127.0.0.1:5173 --timeout-sec 90
```

The retry smoke reuses the golden-path env parsing, backend health checks, and
HTTP client. It also refuses `--env-file .env`, requires `AI_PROVIDER=mock`, and
forces `AI_PROVIDER=mock` into `docker compose` when `--compose` is used.

Expected coverage:

- `GET /api/health` reports mock readiness with no credentials required
- `GET /history` on the frontend returns HTTP 200 with a non-empty SPA body
- `POST /api/generations` creates a T2I Imagen job with the
  `[[mock-fail:imagen]]` sentinel
- the source job reaches `failed` with no assets, `vertex_charged: false`, and
  `error.code: mock_provider_failure`
- `POST /api/generations/{source_id}/retry` returns HTTP 201 with a new job id,
  `retry_of_job_id` set to the source id, and no assets
- `GET /jobs/{retry_id}` on the frontend returns HTTP 200 with a non-empty SPA
  body
- cleanup deletes the retry job first, then the source job, unless `--keep-jobs`
  is passed

## Secret Hygiene

Verification should include checks that `.env`, credential files, generated
media, and runtime assets are not staged or committed.

Useful commands:

```powershell
git status --short --branch
git diff --cached --name-only
git ls-files --others --exclude-standard
```
