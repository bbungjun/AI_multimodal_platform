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

Mock AI and isolated verification require no live Google credentials. Mock AI does
not bypass product authentication; credential-free browser use stops at login.

## Start

Before upgrading an existing checkout, inspect the schema compatibility described
under [G4.2A](#owner-schema-and-admission-g42a). Migration0003 refuses nonempty
generation tables. Do not reset, remove volumes or restart an existing preview to
make it pass. The following startup is for a separately approved compatible local
stack; use the isolated verification commands for this change's QA.

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Expected services:

- `db` healthy
- `migrate` exits successfully after `alembic upgrade head`
- `redis` healthy: Celery broker in database 0 and transient OAuth flows in database 1
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

## Browser Login UX (G3.1)

The workspace now checks `/api/auth/me` before mounting generation/history/ops
pages. Without a real session, credential-free development shows `/login`.
`AI_PROVIDER=mock` does not bypass login. For no-credential authenticated UI
verification use the [test-only HTTP fixture suites](../testing.md#browser-authentication-verification-g31),
not a fake product endpoint, manually injected cookie or invented user profile.

Keep `VITE_API_BASE` empty (recommended) or an exact same-origin root. Custom
prefix/cross-origin values fail closed with a configuration message. Login uses
full-page `/api/auth/google/start?ui=1&return_to=...`; default API callers retain
503 JSON while opt-in failures return to the configured frontend `/login`.
Actual OAuth/proxy/cookie acceptance remains a separate authorized live gate.

Unsaved form input is not persisted and resets on full login navigation, logout,
account change or a locked authentication gate. Saved server jobs are not
deleted/cancelled. A timeout does not prove logout succeeded: use the explicit
retry/logout or state-check action. Ordinary health/job polling is not a session
heartbeat. Five-minute activity validation runs only on visible user activity or
focus; successful logout signals other tabs without account/credential payloads.

G4.2A now also authenticates generation/retry/pipeline/enhance and validates owned
references. Read/list/delete/file/ops still lack complete G4.3 enforcement.
Do not publicly deploy based on login or admission checks alone;
emergency revocation #99 and real browser/proxy readiness remain outstanding.

### Isolated G3.1 generation regression

The historical G3.1 protocol is superseded by the G4.1 authenticated runner below.
Do not reuse its old arbitrary base URL or default-Compose smoke commands.
Historical results remain in the [G3.1 portfolio record](../portfolio/issue-101-authenticated-workspace-ux.md).

## Backend Authentication (G3)

Leave `AUTH_GOOGLE_CLIENT_ID`, `AUTH_GOOGLE_CLIENT_SECRET` and
`AUTH_GOOGLE_REDIRECT_URI` empty for default mock development. Health and
generation remain operational; login start returns `503 auth_not_configured`.
`AI_PROVIDER=mock` selects the AI provider, **not** a mock identity provider:
configured OAuth could still contact Google, so do not populate these settings
for this verification workflow. No browser login is performed here.

Backend-only settings in `.env.example` also define `AUTH_FRONTEND_ORIGIN`,
`AUTH_FLOW_REDIS_URL`, `AUTH_COOKIE_SECURE` and `AUTH_PROVIDER_TIMEOUT_SEC`.
Secure cookies are the default; disabling Secure is accepted only for explicit
`APP_ENV=local|test`. Frontend origin and callback URI must be exact, and
credentialed CORS must not use `*`. Google settings never go to worker,
dispatcher, frontend or migration containers.

Use the credential-free verifier twice, with Docker running and backend dev
dependencies installed:

```powershell
$env:AI_PROVIDER = "mock"
python scripts/verify_auth_sessions.py --env-file .env.example
python scripts/verify_auth_sessions.py --env-file .env.example
```

Each invocation owns a fresh guarded Postgres/Redis project and removes it in
`finally`. Never substitute developer resources. A safe command failure requires
diagnosis before rerun; `cleanup_failed` requires checking resources by the
receipt/project label before removing anything. Never run broad Docker prune.

Redis outage blocks new login but not existing Session checks. Restore Redis
and start a new login; consumed or expired flows are not reconstructed. Google
failure also requires a fresh flow. Disabling Google configuration blocks new
login, **not existing Sessions**. Reverting G3 code requires no schema downgrade
and preserves G2 data. Suspected Session compromise requires the guarded
emergency-revocation operation tracked in
[Issue #99](https://github.com/bbungjun/AI_multimodal_platform/issues/99), which is
not implemented. Live readiness is blocked until that operation and deployment
proxy query-redaction checks are completed. Do not enable live authentication
on the strength of mock verification alone.

Compose disables Redis RDB snapshots and AOF so transient OAuth material never
enters Redis persistence. This applies to broker contents too: do not treat
Redis as a durable queue or promise automatic job recovery after a restart.
Outbox/worker recovery remains a separate operational concern. External Redis
deployments must enforce equivalent no-persistence/backup and access controls
before live OAuth is enabled; G3 does not configure cloud Redis.

### Isolated generation regression

Use the G4.1 runner below for current generation regression. The separate
`verify_auth_sessions.py` command above remains the G3 service-specific verifier.
Do not copy callback URLs, cookies, profiles or raw logs into evidence.

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
python scripts/verify_schema_migrations.py --env-file .env.example --include-reset
```

The verifier owns and removes only its generated `schema-verify-*` project. Never
substitute the default project or an existing volume.

The reset form also verifies preview immutability, exact confirmation, empty
post-reset tables, restored head, fail-closed stale-revision behavior for
backend/worker/dispatcher, User/Session constraints, and downgrade-to-G1
compatibility. Run it twice with fresh generated project names when collecting
release evidence.

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

## Authenticated Isolated Verification (G4.1)

With local Docker running, execute from repository root:

```powershell
python scripts/verify_ownership.py --env-file .env.example --cycles 2
```

Prerequisites: Python, Git, Docker and Compose supporting `!override` (verified
locally with Compose5.0.2). No host backend dependency install is needed for this
standard-library CLI; the existing backend image supplies the seeder dependencies.
The Windows launcher preserves ProgramFiles for Docker plugin discovery, but drops
ambient app credentials and proxy settings. Remote Docker contexts/DOCKER_HOST
are refused. No provider, OAuth or managed Redis service is called.

Each cycle creates an unused `ownership-verify-<12 hex>` namespace, labels every
container/named volume/network, replaces backend ports with one dynamic loopback
binding and inspects all actual bindings before HTTP/seed. Redis /data is tmpfs;
no anonymous Redis volume is needed. The unchanged migrate service upgrades only
this fresh DB. Seeder checks DB name/host, mock/local mode, schema head and empty
tables. It never resets an existing DB. A/B/Master and negative fixtures are
synthetic test profiles, not OAuth account verification or a Master promotion CLI.

Raw Session secrets remain in the coordinator memory. Hashes alone enter the
seeder through stdin; neither form is printed. Scoped requests reject external
URLs, traversal, redirects, proxies and auth-header overrides. Golden, retry and
duplicate I2V requests (including both race requests, polling, Range and delete)
all use that transport. Backend `/me` and logout are real G3 routes, not mocks.

Expected: two JSON receipts, each `auth_checks=12`, `admission_checks=111`, `scenarios=3`,
`execution_checks=20`, `pipeline_checks=4`, `race_checks=3`, `expiry_checks=1`, `passed=true`,
`cleanup=true`. Receipts also identify code/schema revision, generated project,
phase, mock provider and elapsed seconds. Never attach raw Compose/application
logs, SQL exceptions, profiles, prompt payloads, headers or cookie jars as evidence.
A failed check gives a safe phase receipt/nonzero exit, without anonymous fallback.
No-cookie and invalid Sessions must fail. G4.2A extends the original G4.1 harness
with authenticated admission proof; G4.2B adds the execution proof below, not full content access isolation.

Per-cycle work deadline is360s, each original smoke at most90s, HTTP timeout10s,
subprocess at most180s and total cleanup budget90s. Startup/build timeout is a
failure, not a reason to use the developer stack. Manual CI allows20 minutes.

Legacy smoke CLIs now delegate to the complete runner. Old `--compose`,
`--base-url`, frontend URL and keep-job switches refuse; use `--cycles 1|2` instead.
Frontend is not launched and static HTML is not considered UX proof. Run the
unchanged frontend auth/browser suites separately, as described in [testing](../testing.md).

### Owner schema and admission (G4.2A)

At the G4.2A checkpoint, packaged head was `0003_content_ownership`. New Jobs/PromptEnhancements require an
authenticated User owner; Asset ownership comes from its Job. Master uses the same
owner-only mutation policy. Missing/foreign references return identical404;
client-supplied owner/user/role fields return422. Mock mode does not relax these rules.

Both upgrade and downgrade lock jobs/assets/prompt_enhancements/outbox_events in
one transaction, with a5s lock timeout, and require these generation tables empty.
User/Session-only data may remain. A refusal preserves schema/revision/data and
returns `content_ownership_requires_empty_generation_tables` for nonempty content.
There is no implicit Master backfill or nullable transition. Schema-only intermediate
commits must not be deployed separately from their authenticated writers.

Rollback: nonempty downgrade also refuses by design. Preserve data and use a
compatible code/schema pair; do not run older anonymous writers against owner-NOT-NULL
head0003. If existing development data prevents upgrade or downgrade, stop and
request a separate data-preserving migration/rollback decision. No default/preview
DB reset or `down -v` is authorized by this runbook's G4.2A verification procedure.

For proof, run the sequential schema2/auth1/admission2 commands in
[testing](../testing.md#owner-persistence-and-admission-g42a). Only freshly generated,
label-verified projects are eligible for guarded reset or fixture cleanup. During
admission tests the owned worker/dispatcher pause; fixed fixtures and a temporary
outbox-failure trigger prove rollback, then are removed before consumers resume.
Raw secrets, identities, prompt text and HTTP/SQL responses stay out of receipts.

Implementation `e3c98f1` passed two final admission cycles with exact-label resource
counts0. [Issue105](../portfolio/issue-105-owner-persistence-admission.md) records
schema/auth evidence, regression counts, failure analysis and delivery. Worker
reference rechecks/pipeline-race proof are verified by G4.2B below; all read/file/delete/ops access
controls remain G4.3. This is private local mock verification, not public deployment.

### Worker ownership and pipeline proof (G4.2B)

Use the same canonical two-cycle command above, not the destructive schema/reset
verifier. B changes no migration; packaged head remains0003. It checks foreign
worker references on real valid-FK fixtures, two independent pipeline-link sessions
blocked on the child lock, and create/create, create/retry, retry/retry HTTP pairs
blocked on each intended source lock. Only this run's consumers pause/resume.

The fixed holder protocol accepts LF/CRLF JSON lines, times out after20s, and rolls
back on EOF or failure. Host waiter observation including label checks is bounded
by5s; each HTTP request remains10s. Helpers are reaped before guarded project
cleanup. Killing a launcher alone is not evidence that its DB transaction ended.
The original auth/admission/smokes finish before A's fixture Session is expired;
then /me401 and already admitted Job completion are required. B remains valid for
later requests; no fallback/reseed occurs. Real Celery parent/child output bytes,
owner/source relationships and child outbox1 are checked before cleanup.

`ownership_reference_mismatch` fails only the executing nonterminal Job and never
repairs owners. A failed pipeline transaction returns `pipeline_link_failed` while
the parent remains completed; automatic link reconciliation is not implemented.
Do not regenerate a completed parent, relabel an owner or reset the DB to bypass
this condition. Preserve evidence and plan a separate reviewed repair procedure.
Code rollback must retain A-compatible head0003 and acknowledges losing B's worker
protections; do not downgrade/reset developer or preview data.

[Issue107 evidence](../portfolio/issue-107-worker-ownership-invariants.md) records
two complete cycles, Windows CRLF failure/recovery, full regression and delivery.
Public multi-user release still requires G4.3 and the remaining live security gates.

### Failure and owned-project recovery

Normal completion and handled failure run label-checked cleanup and verify zero
owned containers/volumes/networks. Forced process kill, Docker outage or repeated
interrupt during cleanup can prevent finally from completing. Images/build cache
may remain; no broad prune is performed. Developer/preview resources are never
cleanup targets. Treat cleanup=false or missing receipt as incomplete verification.

For manual recovery, take the exact project from the interrupted run's receipt.
If there is no trustworthy project receipt, inspect local project labels first;
do not infer a target from a wildcard or the default Compose name. The following
procedure refuses mismatched ownership labels and never reads container env:

```powershell
# Replace only after matching the interrupted run's safe receipt.
$verifyProject = 'ownership-verify-REPLACE_FROM_RECEIPT'
if ($verifyProject -cnotmatch '^ownership-verify-[0-9a-f]{12}$') { throw 'Invalid target' }
$verifyEndpointPattern = '^(unix:///[^\r\n]+|npipe:////\./pipe/(dockerDesktopLinuxEngine|docker_engine))$'
if ($env:DOCKER_HOST -and $env:DOCKER_HOST -notmatch $verifyEndpointPattern) { throw 'Remote daemon refused' }
$verifyContext = docker context show
if ($LASTEXITCODE -ne 0 -or $verifyContext -notmatch '^[A-Za-z0-9_.-]+$') { throw 'Context failed' }
$verifyEndpoint = docker context inspect $verifyContext --format '{{.Endpoints.docker.Host}}'
if ($LASTEXITCODE -ne 0 -or $verifyEndpoint -notmatch $verifyEndpointPattern) { throw 'Remote daemon refused' }
$verifyLabel = "label=com.docker.compose.project=$verifyProject"
$verifyResources = @()
foreach ($kind in @('container', 'volume', 'network')) {
  $ids = if ($kind -eq 'container') { @(docker --context $verifyContext ps -aq --filter $verifyLabel) }
         else { @(docker --context $verifyContext $kind ls -q --filter $verifyLabel) }
  if ($LASTEXITCODE -ne 0) { throw 'Resource listing failed' }
  foreach ($id in $ids) {
    $selector = if ($kind -eq 'container') { '{{json .Config.Labels}}' } else { '{{json .Labels}}' }
    $labelsJson = docker --context $verifyContext $kind inspect $id --format $selector
    if ($LASTEXITCODE -ne 0) { throw 'Label inspection failed' }
    $labels = $labelsJson | ConvertFrom-Json
    if ($labels.'com.docker.compose.project' -cne $verifyProject -or
        $labels.'creativeops.verifier' -cnotmatch '^[0-9a-f]{32}$') { throw 'Foreign resource' }
    $verifyResources += $labels.'creativeops.verifier'
  }
}
if ($verifyResources.Count -eq 0) { throw 'No resources; nothing to remove' }
if (@($verifyResources | Sort-Object -Unique).Count -ne 1) { throw 'Mixed ownership; stop' }
# Confirm this pinned local context matches the interrupted run's daemon.
# Run only from this repo; no Vertex override, default project or remote daemon.
docker --context $verifyContext compose --project-name $verifyProject --env-file .env.example -f docker-compose.yml down --volumes --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'Cleanup failed; do not claim success' }
foreach ($kind in @('container', 'volume', 'network')) {
  $remaining = if ($kind -eq 'container') { @(docker --context $verifyContext ps -aq --filter $verifyLabel) }
               else { @(docker --context $verifyContext $kind ls -q --filter $verifyLabel) }
  if ($LASTEXITCODE -ne 0 -or $remaining.Count) { throw 'Cleanup not verified' }
}
```

This manual procedure is not an arbitrary-target seeder and must not be used for
the default/preview project. Review any missing/mixed labels instead of bypassing
the guard. Roll back harness changes through a reviewed Git revert; no schema
downgrade or developer DB deletion is necessary. After a harness fix, rerun two
fresh cycles. [Issue103 evidence](../portfolio/issue-103-authenticated-mock-harness.md)
records the Windows plugin-discovery failure, successful runs and remaining gates.

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

## Authenticated Metadata and G4.3A

G4.3A metadata GET/list/delete requires the existing Session. Default generation
list is mine (including Master); only Master may request scope=all and read other
owners. Master cannot delete/retry/reuse other owners. Foreign/missing objects have
the same404. Protected JSON responses, including errors, are private,no-store.

For credential-free verification use the owned harness rather than a product mock
login or manually fabricated cookie:

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_ownership.py --env-file .env.example --cycles 2
if ($LASTEXITCODE) { throw 'Metadata verification failed' }
```

It seeds only hashes in two fresh owned projects and cleans its exact-label resources.
Do not aim it at default/preview DBs or change work360s/cleanup90s budgets to hide a
failure. Preserve first failure evidence and rerun complete cycles after an in-scope fix.
Details: [Issue110](../portfolio/issue-110-metadata-ownership-access.md).

A alone does NOT protect file/Range and ops; G4.3B supplies that enforcement and its
delivery is tracked below. Corrupt relationship pages fail closed404; do not add a Master
bypass. File deletion followed by failed DB commit is still non-atomic. Rollback uses
a private/stopped backend and previous code, not a schema downgrade; older code loses
metadata protection and must not be publicly exposed. No actual rollback/live deployment
was performed by this verification.

## G4.3B file/ops verification

B file/Range/Master ops code and v2 verification are implemented. The original
combined runtime exceeded its work budget; that failure remains recorded.
The v2 verifier splits ownership2 and file-ops2 into four fresh
owned projects, same code revision; work360s/cleanup90s per cycle, suite900s, all1800s.
`--suite all` is the full-acceptance selector; local c05b815 proof passed4/998.187s.
Default ownership preserves the existing manual smoke20-minute budget, but only
explicit all proves complete G4.3B. No CI workflow change or dispatch is authorized.
Do not retry the over-budget combined proof or run any reset against preview/default
resources. Follow the new frozen Goal and [failure/approval record](../portfolio/issue-112-file-ops-access.md).

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 2
```

Require complete=true, two cycles per suite, matching code revision and independent
exact-label cleanup0. Missing/false groups, stale SHA, reused project or failed cleanup
must not be combined manually into success. Diagnostics emit fixed phase timings and
error codes only. Do not paste raw Session/email/prompt/response logs into evidence.
The default command proves ownership only; final G4.3B requires explicit all.
Unattended `/metrics` now returns401 without a Session; do not add a scrape bypass.
Ready PR, final-head CI and actual merge remain separately linked from Issue112.

## G5A/G5B/G5C credit schema, lifecycle/accounting proof and safe rollback

Current code packages `0006_credit_accounting_persistence`. G5A creates empty credit
account/cycle/grant/ledger tables;0005 adds immutable operation receipts;0006 adds
four empty reservation/item/allocation/Usage tables and mutation guards. None of
these migrations backfills Users or connects generation. Start or migrate only an explicitly
chosen environment after checking its revision; Goal verification never migrates
the developer or preview database.

Use `scripts/verify_schema_migrations.py --env-file .env.example --include-reset`
only for its generated `schema-verify-*` project. It proves credit constraints,
append-only ledger behavior, legacy data preservation and guarded reset. Do not
substitute a default Compose project or use `down -v` on development/preview.

Downgrade acquires bounded exclusive locks and proceeds only when all four credit
tables are empty. If any contains data, `credit_foundation_requires_empty_tables`
is the expected safe refusal: preserve the records and deploy a reviewed forward
fix. Never disable the ledger triggers or delete accounting rows to force rollback.
For0006, downgrade to0005 is permitted only when all four accounting tables are
empty; any row causes `credit_accounting_requires_empty_tables`. Preserve populated
data and use a reviewed forward fix. Never disable triggers or delete rows merely
to make downgrade pass. Alembic's control column stays widened so the approved
34-character revision can safely transition back to0005.

Never invoke lifecycle or accounting writes manually against a user DB. Validate
G5B compatibility only with:

```powershell
python scripts/verify_credit_lifecycle.py --env-file .env.example
```

For G5C1 run it once after two schema verifier cycles. The invocation owns a fresh project and proves lazy renewal,
Plan/bonus/replay/expiry, caller rollback and eight observed lock races. Populated
operations deliberately block downgrade to0004. G5B and G5C1 do not debit generation;
For G5C2, run the fixed accounting verifier twice at one clean commit:

```powershell
python scripts/verify_credit_accounting.py --env-file .env.example
python scripts/verify_credit_accounting.py --env-file .env.example
```

Require all eight groups, races8, checks>=160 and resource cleanup0 from each
independent `accounting-verify-*` project. A partial group, prior-SHA result or
single cycle is not completion. Never point the verifier at a developer/preview
database. G5C2 proves reserve/settle/release as an internal Module only; generation
billing remains G6/G7.

Prompt enhancement now requires a client-generated UUID `request_id`. Reusing
the same UUID and identical payload returns the stored result; changing payload,
using another owner's ID, observing an active hold, or replaying a released
attempt returns a fixed409 code. Monthly exhaustion returns402 before provider
execution. Do not delete held rows manually: G6 fails them closed as
`prompt_enhancement_in_progress`; reconciliation is a later operations Goal.

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_prompt_credit.py --env-file .env.example
```

This proof owns a separate labelled Compose project and never adopts the
development database.

## Verify generation credit accounting

For the Imagen/Veo and pipeline credit boundary, run two independent projects:

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_generation_credit.py --env-file .env.example
python scripts/verify_generation_credit.py --env-file .env.example
```

Accept only summaries with all eight groups, races2, checks at least120 and
cleanup zero. The verifier owns disposable labelled resources and refuses a
non-mock provider. It does not validate Vertex quota, provider-reported billing
or a real GCP account.

## Stop

```powershell
docker compose down
```

Use `down -v` only when intentionally removing local database and asset volumes.
## Verify per-User concurrency enforcement

From the repository root, keep the normal development/preview Compose project
running or stopped as-is; the verifier owns a different random project and never
adopts its volumes.

```powershell
$env:AI_PROVIDER = "mock"
python scripts/verify_concurrency.py --env-file .env.example
```

A pass reports eight groups, races/check counts, schema/code revisions and
cleanup. Run it twice at the same committed SHA for release evidence. A 429
`user_concurrency_limit` is the expected public response when held top-level
Reservations reach Free1, Pro3 or Max/Master5. Do not clear held Reservations in
the development DB to make this pass: terminalize the owning operation through
the existing settle/release path, or diagnose an abandoned hold as a separate
recovery incident.

The verifier refuses private env files and forces `AI_PROVIDER=mock`; it must not
be used as evidence of live Vertex capacity, GCP quota or provider billing.

## Verify personal Plan and usage reads

Keep development and preview databases unchanged. The G9A verifier creates and
destroys a separate labelled PostgreSQL project and accepts no target/DSN/source
or keep-volume override:

```powershell
$env:AI_PROVIDER = "mock"
python scripts/verify_personal_usage.py --env-file .env.example
```

A pass requires schema head0006, all eight fixed groups, at least three observed
lock races, at least160 checks and container/volume/network cleanup zero. Run it
twice at the same committed code SHA for release evidence. `GET /api/usage/me`
uses the authenticated actor only; `usage_busy` is retryable contention and
`usage_unavailable` is a fail-closed accounting response. Do not repair grant or
Reservation rows to make a read succeed. This verifier is not evidence for the
G9B UI, live OAuth, exact provider model usage, cloud quota or provider billing.
