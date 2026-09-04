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

## Backend Authentication Verification (G3)

Google is never contacted by automated authentication tests. The production
adapter is exercised with `httpx.MockTransport`, including an ephemeral test
signing key; flow and lifecycle tests inject a verified-identity adapter. There
is no runtime mock-login setting or product bypass route.

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_auth_service.py tests/test_auth_api.py tests/test_google_identity_adapter.py tests/test_oauth_flow_store.py tests/test_verify_auth_sessions_script.py -q
cd ..
python scripts/verify_auth_sessions.py --env-file .env.example
python scripts/verify_auth_sessions.py --env-file .env.example
```

Install backend development dependencies and start Docker first. The verifier
creates two distinct fresh `auth-verify-*` projects, starts only Postgres/Redis,
upgrades to the packaged Alembic head (currently `0005_credit_lifecycle_operations`), then runs host-side integration tests through
ephemeral loopback ports. Tests cover HTTP-to-storage login/me/logout, User
invariants, digest storage, transactional rollback, max-five admission races,
expiry, touch races, one-time flow consumption, Redis outage/recovery and cleanup.
No migration is introduced by G3. The three real-runtime tests intentionally
skip in ordinary pytest without the guarded verifier environment; they execute
against real services in this command, not SQLite or mocks.

Only `.env.example` is accepted. Every lifecycle command is bound to the exact
generated project, collision checks precede startup, and `finally` removes only
that project's containers, network and volumes. Receipts under local/untracked
`.omo/evidence/auth/` contain a code checkpoint, category results and numeric
counts, never raw command output, profile, cookie or OAuth values. Redis ports
are rediscovered after restart because Docker may reassign ephemeral ports.

Existing product generation must also pass the isolated golden-path procedure
in the [local runbook](runbooks/local-mock.md). Test counts, host-specific
limitations and observed latency belong to the
[Issue #98 record](portfolio/issue-98-auth-session-lifecycle.md). Do not infer
browser or live Google verification from these results.

## Browser Authentication Verification (G3.1)

The browser Session module has two mandatory test suites in the existing CI
`verify` job. Playwright is a pinned development dependency, not product login
logic. From `frontend`:

```powershell
npm ci
npm run lint
npm run build
npm run test:auth
npx playwright install chromium
npm run test:auth:browser
```

CI uses Node 20 and `npx playwright install --with-deps chromium`. The module
project launches no browser/server. Chromium launches a fresh strict-port
loopback server on 18101; it never reuses a running developer server. Test
fixtures intercept auth/work HTTP before navigation, block external origins and
unhandled API/files requests, and disable service workers. No real Google login,
profile image, cookie-storage proof or AI provider execution is implied.

Coverage includes checking/anonymous/unavailable, profile validation, safe
return paths and ten-minute optional intent storage, callback URL scrubbing,
single native start, logout ambiguity, five-minute visible activity checks,
12-hour fake-clock idle with zero automatic auth requests, stale account query/
mutation/401 rejection and cross-tab invalidation. Viewports: 1440x900, 920x900,
390x844, 320x720, including keyboard/disclosure focus and overflow assertions.

Trace/video/HAR/storageState and automatic screenshots are disabled. Automatic
DOM error snapshots are disabled and runner output is not retained. Only
explicit masked captures outside the runner output directory are retained under
local/untracked `.omo/evidence/issue-101/screens/`; do not upload the whole folder.
Never include email/profile/prompt/cookie contents in reports. No-test discovery
and skipped mandatory suites are failures, not successful verification.

The backend compatibility extension is tested by `tests/test_auth_api.py`:
default start failures remain 503 JSON; exactly one `ui=1` enables the configured
frontend 303 error redirect with safe headers and flow-cookie cleanup. The rest
of the G3 HTTP/Session contract is unchanged. Browser gating does not protect
backend ownership; G4 is still required. See the
[Issue #101 evidence](portfolio/issue-101-authenticated-workspace-ux.md) for counts,
Windows baseline limitation and separate isolated mock-generation results.

## Prompt Enhancement Evaluation Schemas

The prompt-enhancement benchmark has an isolated package under
`evals/prompt_enhancement/`. Its schema gate does not load `.env`, application
settings, credentials, or provider clients. Run it with an explicit mock
provider marker:

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python verify_mock.py
```

The command accepts no env-file argument and rejects any provider mode other
than `mock`. Tests cover benchmark, manifest, Raw/Enhanced arm, asset, score,
case-statistics and aggregate-report roundtrips; unsupported schema versions;
atomic resumable manifest writes; prompt/file hashes; relative artifact paths;
and ignored run and model-cache directories.

The paired-generation runner uses the same explicit process guard and verifies
`/api/health` reports `mock_provider` before calling the product HTTP APIs:

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python generate_pairs.py --compose --run-id mock-local-001
```

Its focused tests use a fake HTTP boundary to prove alternating Raw/Enhanced
order, matched generation parameters, asset downloads and hashes, terminal
failure checkpoints, default backend cleanup, `--keep-artifacts`, and resume
without duplicate enhancement or generation requests. The versioned
`fixtures/benchmark.failure.v1.jsonl` is reserved for controlled mock-provider
failure validation and is not part of the default success benchmark.

After paired generation reaches `lifecycle=scoring`, run the deterministic mock
metric and statistics stages with the same run id:

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python score_pairs.py --run-id mock-local-001
python summarize.py --run-id mock-local-001
```

The metric tests prove that VQAScore, ImageReward, and TIFA remain separate
synthetic signals; both arms use the same frozen canonical prompt; image scores
are reduced to per-case arm means before paired deltas; and fixed-seed bootstrap
confidence intervals, W/T/L, language/category slices, missing cases, hashes,
and idempotent byte-stable artifacts are reproducible. These mock scores only
validate orchestration and must not be reported as image-quality evidence.

Run the complete pre-Vertex mock evaluation gate with one command:

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python run_mock_e2e.py --compose --run-id mock-gate-local-001
```

The command validates `.env.example` without reading `.env`, runs the success
benchmark through `report.md`, repeats the completed run to prove stable job and
artifact identity, and runs the explicit failure fixture as
`mock-gate-local-001-failure`. It also rejects run/model-cache paths inside the
repository unless Git ignores them and they are absent from staged/visible
status. Focused tests inject an HTTP fake to prove submitted-job resume without
duplicate generation, controlled failure cleanup, no credential access, and no
Vertex or remote-scorer dependency. Operational checks and the paid-run block
are documented in `docs/runbooks/prompt-enhancement-evaluation-gate.md`.

## Prompt Enhancement Offline Scorer Smoke

Actual VQAScore, ImageReward, and TIFA dependencies are isolated in
`evals/prompt_enhancement/offline/`; they are not installed into the backend,
worker, or normal evaluation test environment. The focused contract tests use
fakes and do not download models:

```powershell
cd evals/prompt_enhancement
python -m pytest tests/test_offline_scorers.py -q
```

The tests validate dependency/model revisions, input hashes, complete TIFA QA
coverage, Korean canonical review binding, cache markers, resource failures,
calibration math, real-evidence manifest/report shape, provider isolation, and
the Docker hash-lock boundary.

The manual real-model smoke requires the dedicated Docker image and explicit
model preparation. It makes no Vertex request, but the prepare step downloads
about 10GB of public model snapshots. See
`docs/runbooks/prompt-enhancement-offline-scorers.md` for the exact commands,
minimum CPU memory, GPU limitation, expected artifacts, and failure handling.

## Prompt Enhancement Vertex Pilot Contract

Issue #66의 자동 테스트는 fake HTTP boundary와 fake real scorer만 사용한다. 다음 명령은
Vertex, Gemini, Imagen을 호출하지 않는다.

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
python -m pytest tests/test_vertex_pilot.py tests/test_real_pair_scoring.py -q
python -m pilot --output runs/issue66-preflight/preflight.json
```

테스트는 20-case 영어/한국어/category 균형과 입력 hash, `$20` budget 계산, 20/40/80 request
hard cap, 21번째 enhancement 사전 거부, prompt를 남기지 않는 usage ledger, 별도 post-mock
실행 승인, real score 240개의 resume, 실제 evidence report, TIFA 비열등성 판정과 최종 artifact
hash를 검증한다. 실제 provider 실행은 CI와 기본 local quality gate에 포함하지 않는다.

비용이 없는 실제 Compose dry-run은 v2 benchmark를 명시한다.

```powershell
cd evals/prompt_enhancement
$env:AI_PROVIDER = "mock"
$envFile = (Resolve-Path ..\..\.env.example).Path
python run_mock_e2e.py --compose --env-file $envFile `
  --benchmark benchmark.v2.jsonl --run-id issue66-mock-dry-run
```

유료 실행과 real scorer/final report 절차는
`docs/runbooks/prompt-enhancement-vertex-pilot.md`에서만 인수한다.

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

## Schema Migration and Reset Verification

G1 makes Alembic the only normal schema mutation path. Static and unit checks
run without a database:

```powershell
cd backend
$env:AI_PROVIDER = "mock"
python -m alembic heads
python -m pytest `
  tests/test_alembic_schema.py `
  tests/test_schema_control.py `
  tests/test_verify_schema_migrations_script.py -q
```

The packaged head must be exactly `0006_credit_accounting_persistence`. Application
startup checks are read-only and must return a typed failure for a missing,
empty, outdated, multiple-head, or unreachable schema.

Use only the isolated verifier for destructive migration/reset QA:

```powershell
python scripts/verify_schema_migrations.py --env-file .env.example
python scripts/verify_schema_migrations.py --env-file .env.example --include-reset
```

The verifier requires `AI_PROVIDER=mock`, creates a fresh project whose name
matches `schema-verify-[a-z0-9]{8,32}`, refuses collisions, and always targets that
exact project in cleanup. It must never be replaced with the default developer
Compose project or volume. Receipts under `.omo/evidence/issue-94/` are local,
redacted evidence and are not staged by directory wildcard.

At G2 checkpoint `2a4c8ab`, two fresh `--include-reset` runs passed under
`schema-verify-75c5d479eb4a` and `schema-verify-a0f92adacc0f`. Each run checked
valid identity rows, 11 rejected inserts across 10 named constraints,
downgrade-to-G1 preservation, full-chain round trip, three-process stale
revision refusal/recovery, identity-aware reset, and exact cleanup. The mock
product golden path passed under `schema-verify-golden02`. These results support
`Mock Verified` persistence, not OAuth, cloud, or Vertex verification.

At G5C1 final local checkpoint `b4ce32e`, run the same verifier twice with
`--include-reset`. Each independent receipt must additionally report
`accounting_checks=42`, `accounting_downgrade_cases=4`, accounting mutation guards,
stale lifecycle revision recovery, and cleanup pass with exact project resources0.
The existing G5B lifecycle verifier remains a separate one-run compatibility gate;
it does not prove reserve/settle/release behavior. G5C1 verifies only persistence
and current-head compatibility.

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
- accepted prompt provenance, stable execution-prompt hashing, edited-draft
  tracking, and rejection of stale hidden provider-prompt overrides
- versioned prompt-enhancement benchmark/run/arm/asset/score/summary artifacts,
  including resumable writes and incompatible-version rejection
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

Expected local mock services include the finite `migrate` process plus `db`,
`redis`, `backend`, `dispatcher`, `worker`, and `frontend`. The application
processes start only after `migrate` completes successfully. The `dispatcher` publishes Postgres outbox events to
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

## Authenticated Backend HTTP Smoke (G4.1)

From the repository root with local Docker Desktop/Engine and Compose supporting
`!override` (locally verified 5.0.2), run:

```powershell
python scripts/verify_ownership.py --env-file .env.example --cycles 2
```

The standard-library coordinator owns two fresh PostgreSQL/Redis/backend/worker/
dispatcher runtimes plus the existing migrate service. It never starts frontend.
Only canonical repo `.env.example` is accepted; provider/OAuth configuration is
forced mock/empty. Sessions are generated in memory; only hashes reach the guarded
DB seeder via stdin. A/B/Master real `/api/auth/me` checks and nine negative/logout
checks total 12 per cycle. No dependency override or Google request is involved.

All three scenarios use the same scoped authenticated transport:

- Golden: mock readiness, prompt enhancement, generation201, completed state
  history, asset metadata, PNG signature, Range206, terminal DELETE204.
- Retry: deterministic `[[mock-fail:imagen]]` failure, no assets/charge, retry201
  with new id and correct lineage, terminal retry contract, child-before-parent cleanup.
- I2V: completed T2I source, two concurrent authenticated requests, exactly one201
  and one409 with expected conflict detail, completed I2V and cleanup.

In mock mode, `vertex_charged=true` indicates the mock handler completed, not billing.
HTTP response contents are asserted only in memory, never copied into diagnostics.
Receipts contain revision/project/phase/counts/duration/cleanup booleans only.

Compatibility: all three `smoke_mock_*.py` public CLIs now delegate to this runner
and therefore execute all scenarios. Legacy `--base-url`, `--compose`,
`--frontend-url`, `--timeout-sec` and keep-job switches are rejected. There is no
arbitrary-target authenticated seed path or developer-stack smoke mode. Python
scenario callers must inject `run_smoke(args, client=...)`.

The old retry static SPA-body check was removed; it was not browser/login proof.
Keep frontend regression separate: `npm run lint`, `npm run build`,
`npm run test:auth`, `npm run test:auth:browser`.

Failure/cleanup guards and manual recovery are in the
[local runbook](runbooks/local-mock.md#authenticated-isolated-verification-g41).
The manual smoke workflow uses this same runner twice with contents:read and a
20-minute job timeout, without raw Compose logs or default-project cleanup.

G4.1 originally proved the harness and G3 Session lifecycle only. G4.2A adds
admission and G4.2B adds execution/race proof below; read/list/delete/file/ops remain deferred to G4.3.
See [Issue103 evidence](portfolio/issue-103-authenticated-mock-harness.md)
for actual counts, the baseline Windows Bash-path failure and Linux results.

## Owner Persistence and Admission (G4.2A)

The same canonical ownership runner now preserves auth12 and smoke3, and adds
`admission_checks=111` per cycle: 93 HTTP assertions plus 18 persisted-record checks.
It tests actual G3 Session/Origin rejection on four writers, A/B/Master ownership,
spoof422, foreign/missing404 before semantic errors, own400/409, retry lineage and
actual PostgreSQL outbox-failure rollback. Rejected provider/storage effects are
asserted in unit tests; HTTP/DB counts do not claim to measure provider internals.
Only owned test consumers pause for admission fixtures and resume before smoke.

Run sequentially from repository root, checking each exit code before continuing:

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_schema_migrations.py --env-file .env.example --include-reset
if ($LASTEXITCODE) { throw 'First schema proof failed' }
python scripts/verify_schema_migrations.py --env-file .env.example --include-reset
if ($LASTEXITCODE) { throw 'Second schema proof failed' }
python scripts/verify_auth_sessions.py --env-file .env.example
if ($LASTEXITCODE) { throw 'Auth proof failed' }
python scripts/verify_ownership.py --env-file .env.example --cycles 2
if ($LASTEXITCODE) { throw 'Admission proof failed' }
docker compose --env-file .env.example config --quiet
```

Schema proof covers real NOT NULL/FK/RESTRICT/path uniqueness, identity preservation,
eight nonempty upgrade/downgrade refusals, bounded lock contention, historical
round-trip, stale revision refusal/recovery and guarded reset. Reset is confined
to a newly created verifier database, never developer/preview data. Check exact
project-label container/volume/network counts are zero after each schema run.
Schema/auth receipts use `.omo/evidence/schema/` and `.omo/evidence/auth/`.
Ownership prints safe JSON receipts; this Goal preserved the selected fields in
`.omo/evidence/issue-105/`. Keep these local, not raw logs or Session data.

Focused regression from `backend` with mock: `python -m pytest
tests/test_generation_api.py tests/test_pipeline_api.py tests/test_prompt_api.py
tests/test_ownership_persistence.py -q` (join on one command line). Run the complete
backend suite and unchanged frontend lint/build/auth/browser suites too.
Authoritative Linux result at implementation `e3c98f1`: 658 PASS, 3 pre-existing
guarded-integration skips. Windows has one independently reproduced main Bash
absolute-path failure; it is not skipped or waived in Linux/CI. Full counts,
acceptance mapping and rollback are in [Issue105 evidence](portfolio/issue-105-owner-persistence-admission.md).
No B worker/race or G4.3 complete isolation claim follows from A's passing gates alone.

## Worker Ownership and Pipeline/Race Proof (G4.2B)

The canonical command remains `python scripts/verify_ownership.py --env-file .env.example --cycles 2`.
B adds no migration and does not rerun destructive schema/reset QA. Each fresh cycle
must retain auth12/admission111/scenarios3 and separately report execution20,
pipeline4, race3, expiry1, passed=true and cleanup=true. Nonzero integer groups are
mandatory; a partial cycle is not accepted. Work360s/cleanup90s per cycle and the
total900s budget remain unchanged. Independently check exact project-label
container/volume/network counts0; never use the development or preview project.

| Proof | Evidence boundary |
|---|---|
| P11 worker references | 40 foreign/missing unit combinations, null owner/terminal/optional/attempt/poll/rollback tests; real valid-FK foreign20, no cloud provider |
| P12 Session independence | Authenticated admission, expire only A fixture Session, /me401, admitted Job completed with original owner; no reseed |
| P13 pipeline | Owner/relationship/commit-failure unit cases; real two-Session child-lock overlap and repeated outbox1; Celery parent/child bytes |
| P14 HTTP races | Three distinct sources, host Barrier and two observed DB lock waiters before release;201/409, active1/outbox1, original state preserved |
| P15 complete cycles | Two new projects, all old/new groups required, independent cleanup inspection |
| P16 harness safety | Target/head/provider/identity/operation/records, labels, LF/CRLF, EOF/timeout/broken pipe, safe-count/canary negatives |

Focused commands from `backend` with `AI_PROVIDER=mock`:

```powershell
python -m pytest tests/test_job_handlers.py tests/test_pipeline_link.py tests/test_ownership_execution.py -q
python -m pytest tests/test_verify_ownership_script.py tests/test_mock_auth_support.py tests/test_smoke_mock_golden_path_script.py tests/test_smoke_mock_retry_script.py tests/test_smoke_mock_i2v_duplicate_script.py tests/test_mock_smoke_workflow.py -q
```

Run full backend pytest in a Linux tracked-only archive without workspace/.env/
credential mounts, plus Windows full and unchanged frontend lint/build/auth/browser.
At implementation `ff808b0`, Linux782 PASS/3 pre-existing guarded auth SKIP; Windows
781 PASS/1 Bash absolute-path FAIL/3 existing SKIP. The Windows failure was freshly
reproduced in an untouched `d40a8f7` archive; Linux/CI must pass that test. No new
skip/xfail is allowed. Frontend48+34 PASS. See [Issue107 evidence](portfolio/issue-107-worker-ownership-invariants.md)
for exact checkpoints, commands, failure analysis and final-head CI/merge links.

## G4.3A Metadata Access Verification

At implementation `acb44a9`, two independent owned local mock projects passed
337.73/338.12s. Each preserves auth12/admission111/scenario3/worker20/pipeline4/
race3/expiry1 and adds access_groups8/access_checks348/delete_race_checks2.
The eight groups cover scoped list/detail/pipeline/delete/reference/cache/Session/
query cost. Query measurement is5 content SELECTs for page1/20/100. Two deletion
races observe actual row-lock overlap. Cleanup receipts and independent exact-label
container/volume/network inventories are0; default/preview untouched.

```powershell
# repository root, local Docker only
$env:AI_PROVIDER = 'mock'
python scripts/verify_ownership.py --env-file .env.example --cycles 2
if ($LASTEXITCODE) { throw 'Ownership verification failed' }
# backend, focused Interface/route contracts
Push-Location backend
python -m pytest tests/test_ownership_access.py tests/test_ownership_integration.py -q
$accessExit = $LASTEXITCODE
Pop-Location
if ($accessExit) { throw 'Access contracts failed' }
```

Runtime uses actual Session authentication, PostgreSQL/Redis/Celery with no dependency
override. ASGI tests explicitly use fakes and are not called real-DB evidence.
An initial Master corruption probe incorrectly used mine; it failed and cleaned up,
then explicit all inspection was corrected and both complete cycles rerun.
No metadata proof authorizes file/Range or ops access; those remain G4.3B.
Full Linux tracked-only archive928 PASS/3 existing guarded auth skips; Windows927/
known Bash-path1 FAIL/3 skips, freshly reproduced at untouched c84394a. Linux/CI must
pass that test. Frontend lint/build/Session48/Chromium34 passed unchanged.
[Issue110 record](portfolio/issue-110-metadata-ownership-access.md) tracks CI/merge.

## G4.3B split verification (implemented and locally verified)

The combined B runtime failed at its work budget; partial progress is not success.
The [Issue112 record](portfolio/issue-112-file-ops-access.md) preserves that attempt.
Implemented v2 adds `--suite all`, `ownership` (default), `file-ops` to the same verifier.
Acceptance runs ownership2
then file-ops2 on four new projects at one code revision, requiring a strict complete
aggregate. Legacy8/348/delete-race2 and every old proof remain; F/O/V/E requires all
ten stages for both actors. Single-suite diagnostics cannot close G4.3B.
Work360s/cleanup90s per cycle and900s per suite remain; total four-cycle budget1800s
is explicit. Schema2/auth1, full Linux/backend and unchanged frontend remain separate.
See [B v2 contract](initiatives/g4-ownership-access-control-spec.md) before execution.
Default ownership preserves the existing manual smoke20-minute job budget. Only
explicit `--suite all --cycles 2` proves the complete four-cycle aggregate.

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 2
```

Actual c05b815 aggregate4 PASS/998.187s: ownership333.360/328.859s, file-ops167.500/
167.578s. Each legacy cycle retains348 metadata checks/2 deletion races and old
proof; each file cycle310 checks/FOVE and both actors'10 stages. Exact cleanup0.
Separate unchanged schema2/include-reset and auth1 PASS; Linux1128 PASS/3 existing
guarded skips; frontend48+34 PASS. Windows1127 PASS with sole native127 Bash-path
failure, freshly reproduced on untouched cd654e5. Linux/CI must pass that node.
Final head CI/actual merge are separate delivery evidence, not inferred from local tests.

## G5A credit foundation verification

G5A adds only four empty persistence tables and pure policy; it does not create
accounts, grant credit or charge generation. Unit tests cover immutable Free/Pro/
Max policy, all seven V1 integer rates and exact elapsed 30-day boundaries. Real
PostgreSQL proof covers metadata parity, populated legacy preservation, named
constraints, append-only ledger triggers and three observed uniqueness races.

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_schema_migrations.py --env-file .env.example --include-reset
python scripts/verify_schema_migrations.py --env-file .env.example --include-reset
python scripts/verify_auth_sessions.py --env-file .env.example
python scripts/verify_ownership.py --env-file .env.example --suite all --cycles 2
```

At implementation `b2900a4`, schema work was141.406/119.000s with credit90/
races3 each; reset preview preserved fixtures and execution emptied every table.
Auth passed PostgreSQL, Redis and outage recovery. Ownership/file aggregate was
complete4/993.610s: ownership metadata348/delete races2 twice and file-ops FOVE310/
actors2 twice. All generated projects independently left zero resources; preview
and developer volumes remained. Linux full backend1229 PASS/3 existing guarded
skips; Windows had only the known native127 WSL-path failure, reproduced from
untouched6537025. Frontend lint/build, Session48 and Chromium34 passed unchanged.
See the [Issue115 record](portfolio/issue-115-credit-foundation.md). These are
local mock results, not billing enforcement, live OAuth/provider or cloud proof.

## G5B credit lifecycle verification

G5B exposes only `ensure_cycle`, `change_plan` and `grant_bonus` over a caller-owned
transaction. Two actual PostgreSQL runs use this fixed command:

```powershell
python scripts/verify_credit_lifecycle.py --env-file .env.example
```

The runner accepts no target/DSN/source/keep-volume override. It creates one fresh
`credit-verify-*` project and reports success only when all8 groups,8 observed
lock races and at least80 checks complete. At code65cdbb4 both runs completed320
checks; work16.656/16.828s and cleanup2.938/3.093s, resources0 after each.

The same code passed schema2 with credit90/races3, auth1, ownership/file4 cycles,
Linux1321 PASS/3 guarded skips and frontend Session48/Chromium34. Windows reported
only the existing Bash-path native127, reproduced on untouched a003257. This does
not prove debit/settlement or generation admission; those remain later Goals.

## G5C2 atomic credit accounting verification

The accounting Module is tested through its three-operation Interface and a fixed
local PostgreSQL proof. Run the proof twice at one clean tracked SHA:

```powershell
$env:AI_PROVIDER = 'mock'
python scripts/verify_credit_accounting.py --env-file .env.example
python scripts/verify_credit_accounting.py --env-file .env.example
```

Each invocation owns a fresh `accounting-verify-*` project and accepts no target,
DSN, source, keep-volume or evidence override. Completion requires the eight fixed
groups, eight observed lock races, at least160 checks, head0006, matching code SHA
and exact container/volume/network cleanup0. At code41b1bf3 both final cycles
passed299 checks; work/cleanup were35.172/2.656s and14.829/2.687s.

This proof covers deterministic holds, equal/different replay, complete/partial/
no-deliverable terminals, expired remainder, outer rollback, corruption refusal
and renewal races. It does not prove Job/provider integration or charged generation;
those remain G6/G7.

## Secret Hygiene

Verification should include checks that `.env`, credential files, generated
media, and runtime assets are not staged or committed.

Useful commands:

```powershell
git status --short --branch
git diff --cached --name-only
git ls-files --others --exclude-standard
```
