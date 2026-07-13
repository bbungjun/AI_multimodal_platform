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
- AWS portfolio deployment: no live AWS stack is currently running. The Sydney
  `ap-southeast-2` portfolio stack under AWS account `827913617635` was
  intentionally destroyed on 2026-06-19.
- AWS Terraform: `infra/aws/` contains the Terraform baseline for recreating the
  portfolio stack. The committed defaults keep ECS desired counts at `0`; use
  local ignored tfvars when intentionally enabling live services. The previous
  S3 remote state bucket was also deleted after the state was emptied, so a
  future redeploy must recreate the backend bucket before `terraform init`.
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

## Active Work

As of 2026-07-13, Issue #61 implements versioned prompt-enhancement benchmark
and run artifact contracts on branch `codex/issue-61-eval-artifact-schemas`:

- Added the isolated `evals/prompt_enhancement/` package without changing the
  production backend/worker dependency set or database schema.
- Schema version 1 covers benchmark cases, resumable run manifests, paired
  Raw/Enhanced arm checkpoints, generated assets, per-image metric scores, and
  aggregate reports.
- Run manifests record Git/provider/evidence state, benchmark and prompt hashes,
  enhancer/template/model/scorer versions, generation parameters, lifecycle
  timestamps, retry/failure state, asset hashes, bootstrap settings, and metric
  tie thresholds.
- Manifest and JSONL writers use flushed same-directory temporary files and
  atomic replacement. Loaders reject missing, incompatible, malformed, or
  duplicate records with the artifact path and specific validation error.
- Artifact paths reject absolute, drive-relative, and parent-traversal values.
  `runs/` and `.model-cache/` are ignored; versioned schemas, fixtures, and
  reviewed aggregate reports remain eligible for source control.
- `verify_mock.py` requires explicit `AI_PROVIDER=mock`, accepts no `.env`
  argument, and never imports application/provider clients. Its 17 schema and
  safety tests pass.
- Fresh repository verification passed 351 backend tests with one unrelated
  Windows/bash path test deselected, frontend TypeScript lint and production
  build, Compose mock config, ignore checks, and `git diff --check`. The
  unfiltered 352-test backend run failed only
  `test_release_script_guards_plan_scope_and_uses_terraform_rollback` because
  bash could not resolve the Windows-style script path.
- No live Vertex request, model download, generated media, credential read, or
  provider cost was incurred.

## Last Completed Work

As of 2026-07-13, Issue #60 completed on branch
`codex/issue-60-prompt-execution-provenance` and merged through PR #68 at
`541d93f`:

- The `prompt` stored on a generation `Job` is the exact Imagen/Veo execution
  prompt; legacy hidden `provider_prompt` metadata cannot replace it.
- Job responses expose the execution-prompt SHA-256. Enhancement-linked jobs
  also preserve enhancement/model/template/target provenance and whether the
  user edited the draft before generation.
- Prompt provenance reuses existing JSON fields and does not add a database
  migration or duplicate prompt text into the provenance object.
- `provider_prompt_en` remains audit/reference metadata only, and the final
  generation payload remains the user-reviewed source of truth.
- Focused mock verification passed 90 backend tests, frontend lint/build,
  Compose config, and diff checks without a live provider call.

As of 2026-07-10, Issue #57 completed on branch
`codex/issue-57-milestone-evidence-audit` to close the six-stage platform
reliability milestone against merged source, CI, Terraform, and live runtime
evidence:

- Closeout PR #58 passed its verify workflow before merge.
- The milestone implementation PRs are all merged: PR #50 at `791fa45`, PR #52
  at `7389562`, PR #54 at `80ed664`, and PR #56 at `9f1734f`.
- Merged `main` commit `9f1734f` passed its push workflows: CI run
  `29066671359`, Terraform run `29066671374`, and backend/frontend image scan
  plus SBOM run `29066671378` all completed successfully.
- Personal GCP guard was verified before every write:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- VERIFIED Cloud Build created the final backend with build
  `f2858aa0-7c6d-4811-bbcb-3dba1246626b`, digest
  `sha256:7f91585902a75ca8e378ff61579af6e0ed7701a9ea1aab49efb7cb3f6bfc1a44`,
  and frontend with build `a80e9192-9ca6-44cf-9780-91b3f55acb47`, digest
  `sha256:1534d58e344978c756dae4ba5fbad460a6910406fe67dde859d5a1434b325e01`.
  Both Artifact Registry digests report SLSA build level 3 and two provenance
  records.
- The guarded release plan allowed only API, worker, dispatcher, and frontend
  Deployment image changes. Apply reported `0 added, 4 changed, 0 destroyed`;
  all rollouts and the bounded external health gate passed.
- Live API and frontend Deployments are `2/2`; worker and dispatcher are `1/1`.
  API, worker, and dispatcher run the final backend digest, and frontend runs
  the final frontend digest. Health reports `ok=true`, `ready=true`, DB `up`,
  and `vertex.status=mock_provider`.
- GKE node-pool autoscaling remains `RUNNING` and enabled with min `1`, max `2`.
  API/frontend HPA resources remain intentionally absent after Issue #45's
  enable, k6 observation, and controlled rollback exercise.
- Managed observability remains live: `PodMonitoring` scrapes `/metrics` every
  30 seconds; both HTTP 5xx and prompt-provider alert policies are enabled; the
  `CreativeOps API Reliability` dashboard exists; and availability SLO
  `availability-28d` reports goal `0.995` over `2419200s`.
- Repeating the digest release as a full plan returned `No changes`,
  `release_plan_changes=0`, and `release_plan_only=true`. Fresh local
  verification passed 352 backend tests in mock mode, frontend lint/build,
  Terraform format, Bash syntax, and diff checks.
- GPU node pools, NVIDIA device plugins, GPU telemetry, and distributed
  training operations remain future implementation work. This closeout does
  not claim them as completed experience.
- No live Vertex prompt enhancement, Imagen, or Veo call was run. No credential,
  access token, Secret payload, Terraform state content, local tfvars, or
  database password was printed or committed.

As of 2026-07-10, Issue #55 completed on branch
`codex/issue-55-supply-chain-rollback` to add image supply-chain gates and a
Terraform-aligned release rollback path:

- PR #56 was merged into `main` at merge commit
  `9f1734ffc5d205df5037f091051855000b4643dc`.
- Personal GCP guard was verified before every write:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- Commits `a308e91 feat: add supply chain gates and release rollback` and
  `43a99ff fix: retry release health before rollback` add hosted GitHub Actions
  image scans and SPDX SBOM artifacts, verified Cloud Build configuration,
  digest-only release inputs, a non-secret personal release profile, and an
  automatic Terraform rollback script.
- The hosted image gate scans backend and frontend runtime images with Trivy,
  rejects fixable HIGH/CRITICAL findings, and retains SPDX JSON SBOM artifacts
  for 14 days. Third-party actions are pinned to full commit SHAs and workflow
  permissions are read-only.
- The first hosted scan correctly blocked both images: the frontend's old
  nginx/Alpine runtime had 37 fixable HIGH/CRITICAL OS findings, while the
  backend had five fixable HIGH findings from old Starlette and build tooling
  included in the runtime image. The remediation upgrades the frontend to the
  current official nginx Alpine 3.23 image, converts the backend to a
  production-only multi-stage image, excludes tests and development packages,
  and pins FastAPI 0.139 with Starlette 1.3.1 or newer in the 1.3 line.
- A second scan reduced the remaining findings to four frontend OS packages
  and two backend build packages. Patching the Alpine runtime and removing
  pip/setuptools/wheel from the backend runtime cleared the gate. Final PR
  checks passed for backend scan/SBOM, frontend scan/SBOM, Terraform
  format/validate, and the complete verify workflow.
- FastAPI 0.139 introduced nested included-router context. Runtime metrics now
  resolves that effective route template before falling back to Starlette route
  matching, preserving complete `/api/...` labels without exposing arbitrary
  unmatched request paths.
- The release workflow uses a dedicated self-hosted runner label and protected
  `personal-gcp-production` environment. The release script validates the exact
  personal account/project guard, permits only four Deployment image updates,
  requires Artifact Registry digest references, verifies rollout and bounded
  external health retries, and rolls back to captured running digests through
  Terraform when verification fails.
- Terraform enabled the Container Analysis API with an isolated plan of
  `1 added, 0 changed, 0 destroyed`. Verified Cloud Builds produced backend
  build `d66d53e2-72cf-450b-baf8-f0a142fa881b`, digest
  `sha256:85b49ac248e890fb23d05ecfde81aaa7155b9af0a1b02bfc13ad6b0585457cbc`,
  and frontend build `86bf7e8c-a0ff-4f4b-bcdf-78d307c5bc72`, digest
  `sha256:e42fada2c620314b51a2fbef53c776baff7a4ef7393e7f0de415871c7b860059`.
  Container Analysis returned two provenance records for each digest.
- The first live candidate rollout exposed a transient HTTP 502 immediately
  after Kubernetes rollout completion. Automatic rollback restored all four
  workloads and recovered health, but the event showed that a one-shot health
  probe was too sensitive. The follow-up change added bounded retries before a
  release is rejected.
- A second controlled failure used a deliberately impossible expected provider
  status. Candidate rollout completed, health failed to converge after three
  attempts, and automatic Terraform rollback applied exactly four image
  updates. All API, worker, dispatcher, and frontend rollouts recovered and
  health returned `ready=true`, `vertex.status=mock_provider`; the script
  reported `automatic_rollback_complete=true` and exited non-zero as designed.
- The normal digest release then applied `0 added, 4 changed, 0 destroyed`.
  All four deployments rolled out successfully and external health passed with
  `vertex.status=mock_provider`. A repeated full plan with the same digests
  returned `No changes`, `release_plan_changes=0`, and
  `release_plan_only=true`.
- Fresh verification passed 352 backend tests in mock mode, frontend TypeScript
  lint and production build, Bash syntax, Terraform format, initialization,
  and validation. No live Vertex prompt enhancement, Imagen, or Veo call was
  run, and no credential, token, Secret payload, state content, local tfvars,
  or database password was printed or committed.

As of 2026-07-10, Issue #53 completed on branch
`codex/issue-53-monitoring-dashboard-slo` to add a Terraform-managed
reliability dashboard and availability SLO:

- PR #54 was merged into `main` at merge commit
  `80ed664ad5314a051e28da2fdb73c31685ec33f6`.
- Personal GCP guard was verified before every write:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- Commit `9fcf032 feat: add monitoring dashboard and availability SLO` adds a
  cumulative request-duration histogram, opt-in Cloud Monitoring custom
  service/SLO/dashboard resources, bounded SLI filters, tests, and runbook
  guidance. Follow-up commits exclude ops traffic from reliability signals and
  enforce the Dashboard API's supported threshold/grid JSON contract.
- The default request-based availability SLO is 99.5% over a rolling 28 days.
  It treats eligible HTTP 5xx responses as bad and excludes metrics, ops,
  health, and unmatched routes. The dashboard contains seven widgets for
  throughput, 5xx ratio, p95 latency, provider failures, SLO compliance,
  remaining error budget, and one-hour burn rate.
- Cloud Build ID `b2f1726c-ba2f-429c-9b3e-5b0d5228a955` produced backend
  image `9fcf032` with digest
  `sha256:1aa7aef0f465fbd9275f3451cef70c5daa438abaa38c2dcf8955481cd64a92b0`.
- The histogram rollout plan changed only API, worker, and dispatcher images;
  Terraform reported `0 added, 3 changed, 0 destroyed`. All four deployment
  rollouts succeeded; API/frontend are `2/2`, worker/dispatcher are `1/1`, and
  health remains `ok=true`, `ready=true`, DB `up`,
  `vertex.status=mock_provider`.
- A dedicated alert refinement plan updated only the HTTP 5xx policy to exclude
  `/api/ops/metrics` and `/api/ops/health`; apply reported `0 added, 1 changed,
  0 destroyed`.
- Two bounded batches of 20 read-only `GET /api/generations?limit=1` requests
  returned HTTP 200. Managed Prometheus then returned 20 histogram bucket
  series and a successful p95 query value of `25 ms` for that route.
- The initial SLO enablement plan was exactly `3 added, 0 changed, 0 destroyed`.
  The custom service and SLO were created, but Dashboard API validation rejected
  unsupported XY threshold `color`, then `direction`, fields. Removing those
  fields allowed the dashboard recovery plan (`1 added, 0 changed, 0
  destroyed`) to complete. No workload was changed by either dashboard attempt.
- Cloud Monitoring API evidence: service display name `CreativeOps API`; SLO
  goal `0.995`, rolling period `2419200s`, and bad/total filters present;
  dashboard display name `CreativeOps API Reliability` with all seven expected
  widgets. SLO compliance, budget, and one-hour burn-rate selectors each
  returned one time series with data points.
- `gridLayout.columns` is encoded as the API-canonical string `"2"`; this
  removed the numeric/string permanent diff. Final full Terraform verification
  returned `No changes` with `dashboard_canonical_plan_exit=0`.
- Verification before live rollout: focused monitoring tests passed with 13
  tests; the full backend suite passed with 346 tests; frontend TypeScript lint
  and production build passed; Terraform format and validate passed.
- No live Vertex prompt enhancement, Imagen, or Veo call was run. No prompt,
  request body, credential, access token, Secret payload, Terraform state,
  local tfvars, or database password was printed or committed.

As of 2026-07-10, Issue #51 completed on branch
`codex/issue-51-live-observability-evidence` to validate the managed
observability path in the personal GKE environment:

- PR #52 was merged into `main` at merge commit
  `7389562a80105e1eb04307d177d11632568587d7`.

- Personal GCP guard was verified before every write:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- PR #50 was marked ready and merged into `main` at merge commit
  `791fa45d03cc9d1d3f5259d9f342b4d27eb129c4`.
- Cloud Build produced backend image `791fa45` with build ID
  `6171410b-42e6-44a0-9e6a-ac6739b09c34` and digest
  `sha256:8001191afd70acd3bf7c84f1b977b722372289197a8c1482564486b85e12beb2`.
- The first monitoring rollout applied the new backend image, explicitly
  managed the Monitoring API, and created `PodMonitoring`; Terraform reported
  `2 added, 3 changed, 0 destroyed`. Managed Prometheus PromQL returned a
  successful `creativeops_http_requests_total` query across the API pods.
- The first alert-policy apply exposed a real provisioning dependency: the
  provider-failure policy could not be created before its metric descriptor
  existed. The HTTP 5xx policy was created, while the provider policy returned
  a controlled API validation error.
- Commit `f577028 fix: wire prompt model and seed alert metrics` adds zero-valued
  bounded provider-failure series before the first incident, wires Terraform's
  `ENHANCE_MODEL` through backend settings, and preserves explicit model
  overrides in tests.
- Cloud Build produced the corrected backend image `f577028` with build ID
  `c1429054-2e5c-493f-bce1-2353d87bc95e` and digest
  `sha256:4acb3c46823450f1205c453e9897757a622ec74f397c6459b531507f4ec4b285`.
  A targeted image rollout reported `0 added, 3 changed, 0 destroyed`; after
  collection created all four zero-valued provider series, the full apply
  created the remaining provider-failure policy with `1 added, 0 changed, 0
  destroyed`.
- Controlled failure validation temporarily used `AI_PROVIDER=vertex` and an
  intentionally invalid model identifier. Two bounded batches each sent 17
  successful metrics requests and 3 prompt-enhancement requests. The second
  batch produced a five-minute PromQL increase of 20 requests, 3 HTTP 5xx
  responses, a 15% 5xx ratio, and 3 `vertex_request_invalid` provider failures.
- Both Terraform-managed policies opened incidents at
  `2026-07-10T01:47:06Z`. After restoring `AI_PROVIDER=mock` and
  `ENHANCE_MODEL=gemini-2.5-flash`, the HTTP 5xx incident closed at
  `2026-07-10T01:51:41Z` and the provider-failure incident closed at
  `2026-07-10T01:52:31Z`.
- Recovery apply reported `0 added, 4 changed, 0 destroyed`. All rollouts are
  healthy: API/frontend are `2/2`, worker/dispatcher are `1/1`; backend uses
  `f577028`, frontend uses `e8a3c3d`; health reports `ok=true`, `ready=true`, DB
  `up`, and `vertex.status=mock_provider`.
- Post-recovery Terraform drift verification returned `No changes` with
  `post_recovery_plan_exit=0`. Both alert policies and 30-second
  `PodMonitoring` collection remain enabled.
- Verification: focused prompt/ops tests passed with 29 tests; the complete
  backend suite passed with 342 tests. No prompt text, request body, credential,
  access token, Secret payload, Terraform state, local tfvars, or database
  password was printed or committed.

As of 2026-07-10, Issue #49 completed on branch
`codex/issue-49-managed-prometheus-alerts`; PR #50 was merged into `main` at
merge commit `791fa45d03cc9d1d3f5259d9f342b4d27eb129c4`:

- Merged PR #50:
  `https://github.com/bbungjun/AI_multimodal_platform/pull/50`.
- Implementation commit: `116ff21 feat: add managed Prometheus alerting
  baseline`.
- Added `prometheus-client` and a standard `/metrics` endpoint backed by the
  existing process-local `RuntimeMetrics` source of truth.
- Prometheus output includes HTTP request counters by method, FastAPI route
  template, and status; request duration count/sum; process uptime; and prompt
  provider failures by controlled code, status, and retryability.
- Unmatched HTTP paths collapse to the bounded label `unmatched` so arbitrary
  404 paths cannot create unbounded metric series. No request body, prompt,
  env value, credential, or Secret payload is exported.
- Terraform explicitly enables GKE Managed Service for Prometheus, enables the
  Monitoring API, names the API pod scrape port, and adds a namespace-scoped
  `PodMonitoring` for 30-second `/metrics` collection.
- Added opt-in Cloud Monitoring PromQL policies for sustained application HTTP
  5xx ratio and repeated prompt-provider failure codes. Alert creation remains
  disabled by default with `monitoring_alerts_enabled=false`; notification
  channel resource names are optional inputs.
- The HTTP alert excludes scrape, health-probe, and unmatched-route traffic,
  requires at least 20 application requests in five minutes, and uses a 5%
  5xx threshold. The provider policy requires three failures with the same
  code in five minutes.
- Verification: focused mock tests passed with 8 tests; the full backend suite
  passed with 340 tests; `.venv/bin/python scripts/verify_local.py
  --skip-compose` passed backend tests, frontend lint, and frontend production
  build; Terraform `fmt` and isolated `init -backend=false` plus `validate`
  passed.
- Compose config verification was skipped because Docker CLI is unavailable in
  this WSL environment.
- No GCP write, Terraform plan/apply, Kubernetes write, live prompt request,
  Imagen, or Veo call was run. No `.env`, ADC, service-account JSON, API
  key/private key, Terraform state, `.tfvars`, DB password, Kubernetes Secret
  payload, access token, or credential value was read or printed.

As of 2026-07-10, Issue #47 completed on branch
`codex/issue-47-prompt-reliability`; PR #48 was merged into `main` at merge
commit `11cc0c172749b0ccc568859712f53c06f28f3079`:

- Merged PR #48:
  `https://github.com/bbungjun/AI_multimodal_platform/pull/48`.
- Implementation commit: `41586b6 fix: reject prompt language mismatch after
  retry`.
- Scope was narrowed after review because Issue #30 had already implemented
  provider retry/backoff, invalid JSON repair retry, safe public errors, and
  provider failure metrics for prompt enhancement.
- The remaining gap was that a Korean or English prompt could receive a
  language retry, then still succeed if the retry response ignored the requested
  display language.
- Prompt enhancement now rejects unresolved language mismatch after the single
  language retry with `prompt_enhancement_invalid_response` and reason
  `language_mismatch`.
- API handling records this failure through the existing provider failure
  metrics path, returns a stable public 502 response, and does not persist a
  prompt enhancement row.
- Documentation now calls out language mismatch rejection after one retry in
  `docs/provider-modes.md` and `docs/testing.md`.
- Verification:
  `AI_PROVIDER=mock .venv/bin/python -m pytest
  backend/tests/test_prompt_enhancer.py backend/tests/test_prompt_api.py`
  passed with 22 tests; `cd backend && AI_PROVIDER=mock
  ../.venv/bin/python -m pytest` passed with 334 tests; `git diff --check`
  passed.
- No live prompt enhancement, Imagen, Veo, GCP write, Terraform apply, or
  Kubernetes write was run. No `.env`, ADC, service-account JSON, API
  key/private key, Terraform state, `.tfvars`, DB password, Kubernetes Secret
  payload, access token, or credential value was read or printed.

As of 2026-07-10, Issue #45 completed on branch
`codex/issue-45-hpa-live-evidence`; PR #46 was merged into `main` at merge
commit `8f05e59dcd5e9ffdd741777242a5db07c526922e`:

- Issue #43 / PR #44 was marked ready and merged into `main` at merge commit
  `12cc5cc2244eee39b040ed48bf2726937e5e7932`.
- Personal GCP guard was verified before every GCP write:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- HPA enable Terraform plan used image tag `e8a3c3d`, `api_replicas=2`,
  `api_hpa_enabled=true`, `api_hpa_min_replicas=2`,
  `api_hpa_max_replicas=4`, `api_hpa_cpu_target_utilization=70`,
  `frontend_replicas=2`, `frontend_hpa_enabled=true`,
  `frontend_hpa_min_replicas=2`, `frontend_hpa_max_replicas=4`,
  `frontend_hpa_cpu_target_utilization=70`, `worker_replicas=1`,
  `dispatcher_replicas=1`, `node_count=2`,
  `node_pool_autoscaling_enabled=true`, min `1`, max `2`, and
  `ai_provider=mock`.
- HPA enable plan proposed only the two HPA resources:
  `Plan: 2 to add, 0 to change, 0 to destroy`. Apply completed with
  `2 added, 0 changed, 0 destroyed`.
- Post-apply HPA evidence: HPA count `2`; API/frontend min `2`, max `4`, CPU
  target `70`, current/desired replicas `2/2`, and
  `ScalingActive=True`; nodes `2/2` ready; app pods `6` all `Running`.
- Live URL `http://34.50.26.152` stayed in mock mode. `/api/health` returned
  `ok=true`, `ready=true`, DB `up`, and `vertex.status=mock_provider`;
  `/api/health/live` returned `ok=true`.
- k6 readiness profile passed with HPA enabled using
  `EXPECTED_VERTEX_STATUS=mock_provider` and `READINESS_MAX_VUS=10`: 590
  iterations, 1,770 HTTP requests, 5,310 checks, checks 100.00%, HTTP failure
  rate 0.00%, and p95 request duration `53 ms`.
- `/api/ops/metrics` after k6 showed k6-covered endpoints at error rate `0.0`
  and provider failure count `0`. One scrape also observed a single
  `GET /api/.env` error from an external scan-like request, so the aggregate
  in-memory metrics on that API pod briefly showed `http_errors_total=1` and
  `http_error_rate=0.00056`; no secret file or secret payload was read.
- HPA rollback Terraform plan with `api_hpa_enabled=false` and
  `frontend_hpa_enabled=false` proposed only HPA removal:
  `Plan: 0 to add, 0 to change, 2 to destroy`. Apply completed with
  `0 added, 0 changed, 2 destroyed`.
- Post-rollback verification: HPA count `0`; nodes `2/2` ready; app pods `6`
  all `Running`; `/api/health`, `/api/health/live`, `/api/ops/metrics`, and
  `/api/ops/health` returned HTTP 200; post-rollback Terraform drift check
  returned `post_rollback_plan_exit=0`.
- No live prompt enhancement, Imagen, or Veo generation call was run. No
  `.env`, ADC, service-account JSON, API key/private key, Terraform state,
  `.tfvars`, DB password, Kubernetes Secret payload, access token, or
  credential value was read or printed.

As of 2026-07-10, Issue #43 completed on branch
`codex/issue-43-gke-hpa-readiness`; PR #44 was merged into `main` at merge
commit `12cc5cc2244eee39b040ed48bf2726937e5e7932`:

- Issue #41 / PR #42 was marked ready and merged into `main` at merge commit
  `59fb4119c6979104a36a2993d2521faeddc1eeb4`.
- Issue #43 scope: add explicit, default-off API/frontend HPA support for
  workload-level autoscaling without turning HPA on during routine
  deploy/pause/resume flows.
- Added Terraform HPA variables:
  `api_hpa_enabled=false`, `api_hpa_min_replicas=2`,
  `api_hpa_max_replicas=4`, `api_hpa_cpu_target_utilization=70`,
  `frontend_hpa_enabled=false`, `frontend_hpa_min_replicas=2`,
  `frontend_hpa_max_replicas=4`, and
  `frontend_hpa_cpu_target_utilization=70`.
- Added `kubernetes_horizontal_pod_autoscaler_v2` resources for API and
  frontend, each targeting CPU utilization and using bounded scale-up/scale-down
  behavior. The resources are created only when the corresponding
  `*_hpa_enabled` variable is true.
- Added preconditions so HPA min replicas must be less than or equal to max
  replicas, and the Terraform Deployment replica floor must equal the HPA
  minimum when HPA is enabled. This keeps Terraform's initial desired replica
  count aligned with the HPA controller before load starts.
- Updated `docs/runbooks/gcp-gke.md` and `infra/gcp/README.md` to document the
  workload HPA boundary, HPA/node-pool autoscaling distinction, no-generation
  k6 baseline, temporary Terraform replica drift during active HPA tests, and
  rollback back to fixed replicas.
- Added `backend/tests/test_gcp_hpa_readiness.py`.
- Verification so far:
  `/tmp/creativeops-terraform/terraform -chdir=infra/gcp fmt -recursive
  -check`, `AI_PROVIDER=mock .venv/bin/python -m pytest
  backend/tests/test_gcp_hpa_readiness.py
  backend/tests/test_gcp_autoscaling_readiness.py
  backend/tests/test_gcp_k8s_rollout.py
  backend/tests/test_gcp_cost_control_runbook.py` with 13 tests passing, and
  `AI_PROVIDER=mock ../.venv/bin/python -m pytest` from `backend/` with 332
  tests passing. Terraform verification included backend-less `validate` from
  an ignored temporary copy excluding `.terraform`, `backend.hcl`, Terraform
  state, and `.tfvars`.
- Personal GCP guard was verified before no-apply live Terraform plans:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- No-apply live Terraform plan with current mock live vars and HPA disabled
  returned `No changes` with `hpa_disabled_plan_exit=0`.
- No-apply live Terraform plan with HPA enabled for API/frontend
  (`min=2`, `max=4`, CPU target `70`) proposed only
  `kubernetes_horizontal_pod_autoscaler_v2.api[0]` and
  `kubernetes_horizontal_pod_autoscaler_v2.frontend[0]`, with
  `Plan: 2 to add, 0 to change, 0 to destroy` and
  `hpa_enabled_plan_exit=2`.
- No Terraform apply, kubectl write, live Vertex request, k6 prompt run,
  `.env`, ADC, service-account JSON, API key/private key, Terraform state,
  `.tfvars`, DB password, Kubernetes Secret payload, access token, or
  credential value was read or printed.

As of 2026-07-10, Issue #41 completed on branch
`codex/issue-41-gke-autoscaling-evidence`; PR #42 was merged into `main` at
merge commit `59fb4119c6979104a36a2993d2521faeddc1eeb4`:

- Issue #39 / PR #40 was merged into `main` at merge commit `1e1db90`.
- Personal GCP guard was verified before every write operation:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- The paused live stack from Issue #14 was resumed in two stages to avoid
  scheduling workloads before nodes existed:
  - Stage 1 set the GKE node pool back to `node_count=2`; follow-up evidence
    showed the node pool `RUNNING` with `initialNodeCount=2`.
  - Stage 2 restored app workloads with image tag `e8a3c3d`,
    `api_replicas=2`, `frontend_replicas=2`, `worker_replicas=1`,
    `dispatcher_replicas=1`, `node_count=2`, and `ai_provider=mock`.
    Terraform apply completed with `2 added, 4 changed, 0 destroyed`.
    The added resources were the API/frontend PDBs, and the changed resources
    were the four Kubernetes deployments.
- Post-resume Kubernetes evidence:
  - nodes `2`, ready nodes `2`
  - `creativeops-api` desired/updated/ready/available `2/2/2/2`
  - `creativeops-frontend` desired/updated/ready/available `2/2/2/2`
  - `creativeops-worker` desired/updated/ready/available `1/1/1/1`
  - `creativeops-dispatcher` desired/updated/ready/available `1/1/1/1`
  - app pods `6`, all `Running`
  - API and frontend PDBs each reported `currentHealthy=2`,
    `desiredHealthy=1`, and `disruptionsAllowed=1`
- Live URL `http://34.50.26.152` is serving mock mode:
  `/api/health` returned `ok=true`, `ready=true`, DB `up`, and
  `vertex.status=mock_provider`; `/api/health/live` returned `ok=true`.
- k6 readiness profile passed against the live URL with
  `EXPECTED_VERTEX_STATUS=mock_provider` and `READINESS_MAX_VUS=10`: 588
  iterations, 1,764 HTTP requests, 5,292 checks, checks 100.00%, HTTP failure
  rate 0.00%, and p95 request duration `53.34 ms`.
- `/api/ops/metrics` after k6 readiness returned `http_requests_total=632`,
  `http_errors_total=0`, `http_error_rate=0.0`, and
  `provider_failures_total=0`. Endpoint latency samples included
  `/api/health` p95 `8.35 ms` and `/api/ops/health` p95 `19.01 ms`.
- Bounded GKE node pool autoscaling was applied explicitly with
  `node_pool_autoscaling_enabled=true`,
  `node_pool_autoscaling_min_count=1`, and
  `node_pool_autoscaling_max_count=2`. The Terraform plan changed only
  `google_container_node_pool.general`; apply completed with
  `0 added, 1 changed, 0 destroyed`.
- Post-autoscaling evidence:
  - node pool status `RUNNING`
  - autoscaling enabled `true`, min `1`, max `2`
  - current GKE worker instances `2`, both `RUNNING`
  - Kubernetes nodes `2`, ready nodes `2`
  - deployments and pods remained at the post-resume ready counts
  - `/api/health`, `/api/health/live`, `/api/ops/metrics`, and
    `/api/ops/health` continued to return HTTP 200
  - `/api/ops/metrics` returned `http_requests_total=671`,
    `http_errors_total=0`, `http_error_rate=0.0`, and
    `provider_failures_total=0`
- Post-apply Terraform drift check with the autoscaling live var set passed
  with `plan_exit=0`.
- No live prompt enhancement, Imagen, or Veo generation call was run. No
  `.env`, ADC, service-account JSON, API key/private key, Terraform state,
  `.tfvars`, DB password, Kubernetes Secret payload, access token, or
  credential value was read or printed.

As of 2026-07-10, Issue #39 completed on branch
`codex/issue-39-gke-autoscaling-readiness`; PR #40 was merged into `main` at
merge commit `1e1db90`:

- Issue #14 / PR #38 was marked ready and merged into `main` at merge commit
  `d28b445`.
- Issue #39 scope: make node pool autoscaling explicit and testable without
  enabling autoscaling or changing the paused live state.
- Added Terraform variables for optional node pool autoscaling:
  `node_pool_autoscaling_enabled=false`,
  `node_pool_autoscaling_min_count=0`, and
  `node_pool_autoscaling_max_count=2`.
- Added a dynamic GKE node pool `autoscaling` block that is created only when
  `node_pool_autoscaling_enabled=true`.
- Added a Terraform precondition so autoscaling min count must be less than or
  equal to max count.
- Kept the Issue #36 rollout capacity guardrail intact: multi-replica
  API/frontend rollouts still require fixed `node_count >= 2`.
- Updated `docs/runbooks/gcp-gke.md` and `infra/gcp/README.md` to document
  autoscaling as an explicit operating mode, not a hidden deploy/pause/resume
  side effect.
- Added `backend/tests/test_gcp_autoscaling_readiness.py`.
- Verification:
  `/tmp/creativeops-terraform/terraform -chdir=infra/gcp fmt -recursive
  -check`, `AI_PROVIDER=mock .venv/bin/python -m pytest
  backend/tests/test_gcp_autoscaling_readiness.py
  backend/tests/test_gcp_k8s_rollout.py
  backend/tests/test_gcp_cost_control_runbook.py` with 9 tests passing,
  backend-less Terraform `validate` from an ignored temporary copy excluding
  `.terraform`, `backend.hcl`, Terraform state, and `.tfvars`, `git diff
  --check`, and a no-apply Terraform drift plan against the paused live var set
  with `plan_exit=0`.
- No Terraform apply, kubectl write, live Vertex request, k6 prompt run,
  `.env`, ADC, service-account JSON, API key/private key, Terraform state,
  `.tfvars`, DB password, Kubernetes Secret payload, access token, or
  credential value was read or printed.

As of 2026-07-10, Issue #14 completed on branch
`codex/issue-14-gcp-cost-control`; PR #38 was merged into `main` at merge
commit `d28b445`:

- Issue #36 / PR #37 was marked ready and merged into `main` at merge commit
  `c189bc7`.
- Cleanup mode selected: **temporary demo pause**, not full teardown. The stack
  remains reproducible for later QA/autoscaling work, but app pods and GKE
  worker VMs are scaled to zero.
- Personal GCP guard was verified before write operations:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- Terraform scale-down plan used image tag `e8a3c3d`,
  `api_replicas=0`, `frontend_replicas=0`, `worker_replicas=0`,
  `dispatcher_replicas=0`, `node_count=0`, and `ai_provider=mock`.
  The plan proposed `0 to add, 6 to change, 2 to destroy`.
- Terraform apply completed with `0 added, 6 changed, 2 destroyed`. Changed
  resources were the general GKE node pool, backend ConfigMap, and four
  deployments; destroyed resources were the API/frontend PDBs that only exist
  for multi-replica rollouts.
- Post-apply verification:
  - node pool status `RUNNING`, node count `0`
  - Kubernetes nodes `0`
  - deployments `creativeops-api`, `creativeops-frontend`,
    `creativeops-worker`, and `creativeops-dispatcher` each have replicas `0`
  - app namespace pods `0`
  - PDBs `0`
  - frontend `LoadBalancer` service intentionally remains at `34.50.26.152`
  - no `gke-creativeops` Compute Engine worker instances were listed
- Expected retained resources for temporary pause remain present: Cloud SQL
  `RUNNABLE`, Redis `READY`, GCS assets bucket, Terraform state bucket, and
  backend/frontend Artifact Registry repositories.
- Post-apply Terraform drift check with the same scale-down var set passed with
  `plan_exit=0`.
- Updated `docs/runbooks/gcp-gke.md` and `infra/gcp/README.md` so temporary
  demo pause explicitly includes `node_count=0`, documents expected retained
  resources, and distinguishes pause from full `terraform destroy`.
- Added `backend/tests/test_gcp_cost_control_runbook.py` to keep the
  cost-control runbook boundary covered.
- Verification so far: `AI_PROVIDER=mock .venv/bin/python -m pytest
  backend/tests/test_gcp_cost_control_runbook.py
  backend/tests/test_gcp_k8s_rollout.py` with 6 tests passing, and
  `git diff --check`.
- No live prompt enhancement, Imagen, or Veo generation call was run. No `.env`,
  ADC, service-account JSON, API key/private key, Terraform state, `.tfvars`,
  DB password, Kubernetes Secret payload, access token, or credential value was
  read or printed.

As of 2026-07-10, Issue #36 completed on branch
`codex/issue-36-gke-rollout-capacity`; PR #37 was merged into `main` at merge
commit `c189bc7`:

- Issue #34 / PR #35 was marked ready and merged into `main` at merge commit
  `9cbd72519d25909792bab429ea9d436f6d32c939`.
- Issue #36 scope: prevent future Terraform plans from combining
  readiness-gated multi-replica API/frontend rollouts with a single-node GKE
  pool, which caused the 2026-07-09 live rollout capacity failure.
- Added a Terraform `precondition` on the general GKE node pool: if
  `api_replicas > 1` or `frontend_replicas > 1`, `node_count` must be at least
  `2`; otherwise Terraform fails early with an `Insufficient cpu`-oriented
  operator message.
- Updated `docs/runbooks/gcp-gke.md` and `infra/gcp/README.md` to make
  `node_count=2` part of the user-facing rollout contract and to include it in
  mock and Vertex two-replica apply examples.
- Added regression coverage in `backend/tests/test_gcp_k8s_rollout.py`.
- Verification so far: `/tmp/creativeops-terraform/terraform -chdir=infra/gcp
  fmt -recursive -check`, `AI_PROVIDER=mock .venv/bin/python -m pytest
  backend/tests/test_gcp_k8s_rollout.py`, and backend-less Terraform
  `validate` from an ignored temporary copy that excluded `.terraform`,
  `backend.hcl`, Terraform state, and `.tfvars`.
- No GCP apply, kubectl write, live Vertex request, k6 prompt run, `.env`, ADC,
  service-account JSON, API key/private key, Terraform state, `.tfvars`, DB
  password, or Kubernetes Secret payload was read or printed.

As of 2026-07-09, Issue #34 completed on branch
`codex/issue-34-live-rollout-safety-evidence`; PR #35 was merged into `main` at
merge commit `9cbd72519d25909792bab429ea9d436f6d32c939`:

- Issue #32 / PR #33 was merged into `main` at merge commit
  `e8a3c3d967535bb69db47ca068ba53e71c023e73`.
- Personal GCP guard was verified before write operations:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- Built and pushed backend image with Cloud Build ID
  `4ad5d2f5-8dba-4a39-a6b2-57aac374f712`:
  `asia-northeast3-docker.pkg.dev/krafton-vertex-live-3108/creativeops-portfolio-backend/creativeops-backend:e8a3c3d`
  with digest
  `sha256:fa0cc129523513888a0ba86e88b17b1736a3ceceff7d6676932a7a9599f17655`.
- Built and pushed frontend image with Cloud Build ID
  `0f053ab7-1b83-4279-8fe5-ec5ac7980a2a`:
  `asia-northeast3-docker.pkg.dev/krafton-vertex-live-3108/creativeops-portfolio-frontend/creativeops-frontend:e8a3c3d`
  with digest
  `sha256:4aae9833a2c2a875430e407537f66510db9f84fb54eb28efe2c1a1c24691e663`.
- Initial Terraform rollout plan for image tag `e8a3c3d`,
  `api_replicas=2`, `frontend_replicas=2`, `worker_replicas=1`,
  `dispatcher_replicas=1`, and `ai_provider=vertex` proposed
  `2 to add, 4 to change, 0 to destroy`: API/frontend PDBs plus image/probe
  updates for API, worker, dispatcher, and frontend.
- The first apply partially progressed but failed: API exceeded its deployment
  progress deadline and worker reported `1 replicas wanted; 0 replicas Ready`.
  Kubernetes events showed `Insufficient cpu` on the single-node
  `e2-standard-2` node pool. The old API pods kept `/api/health` serving
  `ready=true`, but `/api/health/live` returned 404 until new API pods entered
  service, and the worker was unavailable during the capacity shortage.
- Follow-up Terraform plan/apply added rollout capacity by setting
  `node_count=2`. The apply completed with `0 added, 1 changed, 0 destroyed`.
- Post-capacity Kubernetes verification found two Ready nodes. All deployments
  recovered on image tag `e8a3c3d`: API `READY=2/2`, frontend `READY=2/2`,
  worker `READY=1/1`, and dispatcher `READY=1/1`; each deployment reported
  `updated == desired` and `available == desired`.
- API and frontend PDBs are active with `minAvailable=1`, `currentHealthy=2`,
  `desiredHealthy=1`, and `disruptionsAllowed=1`.
- Live URL remains `http://34.50.26.152` and the stack remains in
  `AI_PROVIDER=vertex`.
- Live `/api/health` returned `ok=true`, `ready=true`, DB `up`, and
  `vertex.status=ready`; live `/api/health/live` returned `ok=true`.
- Live `/api/ops/metrics` after k6 readiness returned
  `requests_total=705`, `errors_total=0`, `error_rate=0.0`,
  `/api/health` p95 latency `9.1 ms`, `/api/ops/health` p95 latency
  `17.55 ms`, and provider failure count `0`.
- k6 readiness profile passed against the live URL with
  `READINESS_MAX_VUS=10`: 640 iterations, 1,920 HTTP requests, 5,760 checks,
  checks 100.00%, HTTP failure rate 0.00%, and p95 request duration
  `23.07 ms`.
- Post-apply Terraform drift check with the live var set, including
  `node_count=2`, passed with `plan_exit=0`.
- No live prompt enhancement, Imagen, or Veo generation call was run. No `.env`,
  ADC, service-account JSON, API key/private key, Terraform state, `.tfvars`,
  DB password, Kubernetes Secret payload, access token, or credential value was
  read or printed.

As of 2026-07-09, Issue #32 completed on branch
`codex/issue-32-gke-rollout-safety`; PR #33 was merged into `main` at merge
commit `e8a3c3d967535bb69db47ca068ba53e71c023e73`:

- Implementation commit: `bf09d1f feat: add gke rollout safety baseline`.
- PR #31 for Issue #30 was marked ready and merged into `main` at merge commit
  `5085195`.
- Issue #32 scope: connect prompt enhancement reliability work to safer GKE
  deployment operations for API/frontend image or runtime-config changes.
- Added process-only `GET /api/health/live` for Kubernetes liveness so external
  DB or Vertex readiness failures do not trigger process restarts.
- Updated API and frontend Kubernetes deployments to explicit
  readiness-gated `RollingUpdate` with `maxUnavailable=0`, `maxSurge=1`,
  `min_ready_seconds=5`, and `progress_deadline_seconds=180`.
- Added API/frontend liveness probes and multi-replica PodDisruptionBudgets that
  are created only when the corresponding replica count is greater than one.
- Documented that worker/dispatcher rollout evidence is task-safety and
  singleton-outbox safety, not HTTP zero-downtime evidence.
- Updated `docs/runbooks/gcp-gke.md` and `infra/gcp/README.md` with rollout
  verification, metrics comparison, and rollback guidance.
- Focused verification passed:
  `AI_PROVIDER=mock .venv/bin/python -m pytest backend/tests/test_health.py
  backend/tests/test_gcp_k8s_rollout.py`.
- Fresh mock/local verification passed:
  `AI_PROVIDER=mock .venv/bin/python -m pytest backend/tests` with 322 tests,
  `npm run build`, Windows Docker CLI
  `docker compose --env-file .env.example config --quiet`,
  Terraform `init -backend=false`, `fmt -recursive -check`, `validate`, and
  `git diff --check`.
- Terraform `fmt -recursive` was applied with the Windows Terraform binary.
- The first sandboxed full backend test run hung because this managed sandbox
  did not complete `asyncio.to_thread`; rerunning the same mock test command
  outside the sandbox passed.
- No GCP write, live Vertex request, k6 prompt run, `.env`, ADC,
  service-account JSON, API key/private key, Terraform state, `.tfvars`, DB
  password, or Kubernetes Secret payload was read or printed.

As of 2026-07-09, Issue #30 completed on branch
`codex/issue-30-prompt-enhancement-reliability` to harden prompt enhancement
provider failure handling:

- PR #31 was merged into `main` at merge commit `5085195`.
- Implementation commit: `8f91727 fix: harden prompt enhancement reliability`.
- PR #29 for Issue #28 was merged into `main` at merge commit
  `743cf5c5ca8353a1c510afba17e011e2eb09c58c`.
- Issue #30 scope: treat Gemini prompt enhancement 429s, transient provider
  failures, and invalid/malformed response payloads as expected operating
  conditions with testable retry/repair behavior and safe public errors.
- Prompt enhancement provider calls now use the shared `PROVIDER_RETRY_*`
  backoff policy for retryable Vertex failures such as 429 rate limits and
  transient 5xx/timeouts.
- Invalid Gemini prompt enhancement payloads now get one strict JSON repair
  retry for malformed JSON, missing text, parsed payload shape errors, or
  schema validation failures before returning the stable public
  `prompt_enhancement_invalid_response` error.
- Prompt enhancement API error handling still records only public provider
  failure code/status/retryability in runtime metrics and does not persist a
  prompt enhancement row on provider failure.
- Added tests for schema-invalid repair success, schema-invalid repair
  exhaustion, provider 429 retry success, provider 429 retry exhaustion, and
  invalid-response metrics recording.
- Fresh mock/local verification passed:
  `AI_PROVIDER=mock .venv/bin/python -m pytest backend/tests` with 318 tests,
  `npm run build`, and Windows Docker CLI
  `docker compose --env-file .env.example config --quiet`.
- `AI_PROVIDER=mock python -m pytest ...` failed before verification because
  this WSL environment has no `python` alias; `.venv/bin/python` was used
  instead.
- Linux `docker` is not installed in this WSL environment; Windows
  `docker.exe` was used only for `.env.example` Compose config validation.
- No GCP write, live Vertex request, k6 prompt run, `.env`, ADC,
  service-account JSON, API key/private key, Terraform state, `.tfvars`, DB
  password, or Kubernetes Secret payload was read or printed.

As of 2026-07-09, Issue #28 is in progress on branch
`codex/issue-28-observability-rollout-handoff` to record the live rollout of
the observability baseline:

- PR #27 for Issue #26 was marked ready and merged into `main` at merge commit
  `67abc7cc0619f34523863dea5d896f7405f3d48b`.
- Personal GCP guard was verified before write operations:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- Built and pushed backend image with Cloud Build ID
  `36a80e98-aa03-4e01-b7e8-eef10d79a9b7`:
  `asia-northeast3-docker.pkg.dev/krafton-vertex-live-3108/creativeops-portfolio-backend/creativeops-backend:67abc7c`
  with digest
  `sha256:c05bfbbc3bbaed993796f2fa0b358c1aa5aac470bd88cce27e53e753d780cdb3`.
- Built and pushed frontend image with Cloud Build ID
  `86845a41-7f8e-466b-8358-85cadf43ec6a`:
  `asia-northeast3-docker.pkg.dev/krafton-vertex-live-3108/creativeops-portfolio-frontend/creativeops-frontend:67abc7c`
  with digest
  `sha256:2d0d880d29a1cd5ed50bf7e931cbb1a64ae949d8cc7e793592e6247ff8e942c9`.
- Terraform plan changed only four Kubernetes deployments in place: API,
  worker, dispatcher, and frontend image tags from `998d40d` to `67abc7c`.
  Terraform apply completed with `0 added, 4 changed, 0 destroyed`.
- Kubernetes rollout status passed for `creativeops-api`, `creativeops-worker`,
  `creativeops-dispatcher`, and `creativeops-frontend`; each deployment reported
  `READY=1`, `UPDATED=1`, and `AVAILABLE=1`.
- Confirmed all four deployments run image tag `67abc7c`.
- Post-apply Terraform drift check passed with `plan_exit=0`.
- Live URL remains `http://34.50.26.152` and the stack remains in
  `AI_PROVIDER=vertex` with one replica per workload.
- Live `/api/health` returned `ok=true`, `ready=true`, DB `up`, and
  `vertex.status=ready`.
- Live `/api/ops/metrics` returned HTTP runtime metrics, including
  `requests_total=19`, `errors_total=0`, `error_rate=0.0`,
  `/api/health` p95 latency `188.03 ms`, and provider failure count `0`.
- Live `/api/ops/health` includes additive `runtime` metrics and reported
  `jobs.completed=2`, `outbox.published=3`, and no recent failures.
- No `.env`, ADC, service-account JSON, API key/private key, Terraform state,
  `.tfvars`, DB password, or Kubernetes Secret payload was read or printed.

As of 2026-07-09, Issue #26 completed on branch
`codex/issue-26-observability-baseline`; PR #27 was merged into `main` at merge
commit `67abc7cc0619f34523863dea5d896f7405f3d48b`:

- PR #25 for Issue #24 was marked ready and merged into `main` at merge commit
  `e5f09b3186e85d683635140c5e36c5cbbcdf51a9`.
- Issue #26 scope: add a small, testable observability baseline before deeper
  prompt reliability work.
- Added in-memory runtime metrics for API request throughput, HTTP error rate,
  per-endpoint status counts, latency samples, and provider failure counts by
  public code/status.
- Added request metrics middleware and `GET /api/ops/metrics`; `GET
  /api/ops/health` now includes the same runtime snapshot under additive field
  `runtime`.
- Prompt enhancement `VertexServiceError` handling now records provider failure
  counters without logging response bodies, prompts, credentials, or Secret
  payloads.
- Updated local mock and GCP GKE runbooks to inspect `/api/ops/metrics` before
  and after smoke or k6 runs.

As of 2026-07-09, Issue #24 completed on branch
`codex/issue-24-practical-ops-standards`; PR #25 was merged into `main` at merge
commit `e5f09b3186e85d683635140c5e36c5cbbcdf51a9`:

- PR #23 for Issue #22 was marked ready and merged into `main` at merge commit
  `594f61766b6d8bef3b5a024db0dab438158aa194`.
- Issue #24 scope: codify practical production-grade implementation standards
  so future work is judged by platform engineering quality, not demo-only
  functionality.
- Updated `AGENTS.md` with a `실무 수준 구현 기준` section covering
  Kubernetes probes/resources/rollout impact, Terraform/IaC reproducibility,
  guarded automation, observability beyond health endpoints, k6 baseline/stress
  reporting, AI provider retry/failure handling, security/secret discipline,
  CI/CD rollback readiness, performance/cost/quota decisions, and accurate
  separation of implemented evidence from planned GPU work.
- Next recommended implementation issue after #24: an observability baseline
  that makes latency, error rate, throughput, queue/backlog, worker state,
  provider failure codes, and quota/rate-limit signals visible for the live
  GKE/Vertex stack.

As of 2026-07-08, Issue #22 completed on branch
`codex/issue-22-k6-load-test`; PR #23 was merged into `main` at merge commit
`594f61766b6d8bef3b5a024db0dab438158aa194`:

- Started from `main` at PR #21 merge commit
  `44b0875 Merge pull request #21 from
  bbungjun/codex/issue-13-gcp-vertex-readiness`.
- Added `scripts/k6/creativeops_gcp_load.js` with three profiles:
  `readiness`, `prompt`, and `mixed`.
- Added `docs/runbooks/k6-gcp-load-test.md` with Linux k6 commands and the WSL
  workaround for running Windows `k6.exe` from a Windows temp copy of the
  script.
- Updated `AGENTS.md` to make the Hyundai AutoEver Platform Engineer /
  `AI 플랫폼 구축/운영` target explicit: future work should strengthen
  Kubernetes/GKE operations, automation, observability, load testing, reliability,
  and GPU-infrastructure readiness while clearly separating implemented evidence
  from planned GPU work.
- Live target used for k6 verification: `http://34.50.26.152`, still running in
  `AI_PROVIDER=vertex`.
- `PROFILE=readiness`, `EXPECTED_VERTEX_STATUS=ready`,
  `READINESS_MAX_VUS=10` passed: 1764 HTTP requests, 5292 checks, checks
  100.00%, HTTP failure rate 0.00%, p95 request duration 53.92 ms.
- `PROFILE=prompt`, `ALLOW_VERTEX_PROMPT=1`, `PROMPT_RATE=6`,
  `PROMPT_DURATION=2m` failed as a stress run: 11 HTTP requests, 9 successes,
  2 failures, checks 81.81%, HTTP failure rate 18.18%, p95 request duration
  23.9 s, 1 dropped iteration.
- `PROFILE=prompt`, `ALLOW_VERTEX_PROMPT=1`, `PROMPT_RATE=3`,
  `PROMPT_DURATION=2m` also failed: 7 HTTP requests, 6 successes, 1 failure,
  checks 85.71%, HTTP failure rate 14.28%, p95 request duration 23.32 s.
- Recent API logs for failed prompt calls showed public error codes only:
  `vertex_rate_limited` with status 429 during the 6/min run, and
  `prompt_enhancement_invalid_response` with no provider status during both
  runs. No response bodies, Secret payloads, or credential files were printed.
- No Imagen or Veo load test was added or run.

As of 2026-07-08, Issue #13 completed on branch
`codex/issue-13-gcp-vertex-readiness`; PR #21 was merged into `main` at merge
commit `44b0875`, and the live personal GCP stack is now in Vertex mode:

- Merged PR #20 for Issue #12 into `main` at merge commit
  `deb29c8b4dc21ad5cd0a158784c51b1e6b30c6e1`, then created the Issue #13 branch
  from updated `main`.
- Personal GCP guard was verified before write operations:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- Added a runtime ConfigMap hash annotation for API, worker, and dispatcher
  pod templates so changing `AI_PROVIDER` through Terraform rolls the affected
  workloads instead of leaving existing pods on stale environment values.
- Applied Terraform with the existing deployed images and `ai_provider=vertex`.
  The plan changed only `creativeops-backend-env` and the API, worker, and
  dispatcher deployment templates.
- Live frontend URL remains `http://34.50.26.152`.
- `/api/health` now reports DB up and Vertex ready:
  `vertex.status=ready`, `credentials=available`, `project=configured`, and
  `location=us-central1`.
- Workload Identity evidence: API, worker, and dispatcher run as Kubernetes
  service account `creativeops-app`; API/worker pod specs have no
  `GOOGLE_APPLICATION_CREDENTIALS` env var and no service-account JSON volume
  mount. No credential file was read, mounted, or printed.
- Ran exactly one Gemini prompt enhancement request through the live frontend
  URL. It returned HTTP 201, enhancement id
  `c7cc72cc-e898-4a3b-a0bd-8072d1d88897`, non-empty enhanced text, and usage
  metadata `tokens_in=975`, `tokens_out=120`.
- No Imagen or Veo live generation was run.
- Fresh verification passed:
  `terraform -chdir=infra/gcp fmt -recursive -check`,
  `terraform -chdir=infra/gcp validate`,
  `terraform -chdir=infra/gcp plan -detailed-exitcode` with
  `plan_exit=0`, `/api/health`, `/api/ops/health`, the one Gemini prompt
  enhancement call, and Kubernetes workload identity/spec checks without
  printing Secret payloads.
- Current live workload state: API, worker, dispatcher, and frontend are each
  running at 1 replica in namespace `creativeops-portfolio`. This live stack is
  now in Vertex mode and can incur GCP/Vertex cost until changed back to mock,
  scaled down, or destroyed.

As of 2026-07-08, Issue #12 completed on branch
`codex/issue-12-gcp-mock-smoke` with the first personal GCP mock deployment:

- Personal GCP guard was verified before write operations:
  `youngjun3108@gmail.com` / `krafton-vertex-live-3108`.
- PR #19 for Issue #11 was merged before starting this branch; local `main`
  was fast-forwarded to merge commit
  `998d40dbd13f3e21dddeedc3da1f35f53cf69e5d`.
- Docker Desktop WSL integration was unavailable, so backend and frontend
  images were built and pushed with Cloud Build instead of local Docker.
- Deployed image tag: `998d40d`.
- Backend image:
  `asia-northeast3-docker.pkg.dev/krafton-vertex-live-3108/creativeops-portfolio-backend/creativeops-backend:998d40d`
  with digest
  `sha256:85f65f76ce5bf5aec035179dfdeb89842c229bbcda8128eab561009987668e49`.
- Frontend image:
  `asia-northeast3-docker.pkg.dev/krafton-vertex-live-3108/creativeops-portfolio-frontend/creativeops-frontend:998d40d`
  with digest
  `sha256:d1cf0305b919b4932c64631262d533927df290b5ce948fef51e508405e2b6ada`.
- Bootstrapped remote Terraform state bucket
  `creativeops-terraform-state-krafton-vertex-live-3108` with ignored local
  `infra/gcp/backend.hcl`.
- Used Linux Terraform 1.14.8 from a temporary local tool directory because
  Windows `terraform.exe` could not reliably write the GCS backend lock from
  WSL.
- Applied the GCP stack in `AI_PROVIDER=mock`: Artifact Registry, VPC/private
  service access, GKE, node pool, GCS asset bucket, Memorystore Redis, private
  Cloud SQL PostgreSQL, Secret Manager metadata, Workload Identity, and
  Kubernetes workloads.
- Cloud SQL is private at `10.218.0.3`; database `multimodal` exists. The app
  DB password and `DATABASE_URL` were created/rotated without printing values,
  added to Secret Manager, and applied to Kubernetes Secret
  `creativeops-runtime-secrets`.
- Live frontend URL: `http://34.50.26.152`.
- Current live workload state: API, worker, dispatcher, and frontend are each
  running at 1 replica in namespace `creativeops-portfolio`. This live stack
  can incur GCP cost until scaled down or destroyed.
- Fresh live verification passed:
  `/api/health`, `/api/ops/health`, and
  `.venv/bin/python scripts/smoke_mock_golden_path.py --base-url
  http://34.50.26.152 --timeout-sec 180`.
- Fresh repository verification passed:
  `terraform -chdir=infra/gcp fmt -recursive -check`,
  `terraform -chdir=infra/gcp validate`,
  `terraform -chdir=infra/gcp plan -detailed-exitcode` with
  `plan_exit=0`, `.venv/bin/python scripts/verify_local.py --env-file
  .env.example --skip-compose`, `git diff --check`, and
  `git diff --cached --check`.
- No Vertex live generation call was run; health reports mock provider mode.
- Implementation adjustments made during deployment: added Cloud Build API and
  frontend Cloud Build config, set Cloud SQL edition to `ENTERPRISE`, serialized
  Workload Identity IAM after GKE cluster creation, disabled Terraform PVC
  bound waiting, lowered API/worker CPU requests for the single-node mock
  deployment, and switched API/worker rollout strategy to `Recreate`.
- WSL/kubectl note: the Windows `gke-gcloud-auth-plugin` was not available, so
  Kubernetes operations used a temporary token kubeconfig generated from the
  personal gcloud login. The temp file was removed after use.
- PR #20 was reviewed, merged, and closed Issue #12 before Issue #13 started.

As of 2026-07-08, Issue #11 added the deployment scripts and runbook layer on
branch `codex/issue-11-gcp-deployment-runbooks`:

- Started from `main` at PR #18 merge commit
  `c528046 feat: add gke workloads (#18)`.
- Added `scripts/use_personal_gcp.ps1` and shared guard helpers so GCP
  deployment shells set `CLOUDSDK_CONFIG`, `KUBECONFIG`, project env vars, and
  clear local credential-file env vars before any guarded action.
- Guarded GCP helpers verify the personal account
  `youngjun3108@gmail.com` and personal project `krafton-vertex-live-3108`, and
  explicitly refuse the known team account/project.
- Added `scripts/build_push_gcp_images.ps1` for backend/frontend Docker image
  build and Artifact Registry push using the Terraform repository naming
  contract.
- Added `scripts/bootstrap_gcp_runtime_secrets.ps1` to create or rotate the
  Cloud SQL app user password through the Cloud SQL Admin API, add a Secret
  Manager `DATABASE_URL` version, and apply the Kubernetes runtime secret
  without printing secret values.
- Added `docs/runbooks/gcp-gke.md` and updated `infra/gcp/README.md` plus the
  deployment plan to use the guarded scripts.
- Updated `scripts/verify_local.py` to use the invoking Python executable for
  backend tests, so environments without a `python` alias can still run the
  quality gate.
- No live GCP apply, API enable, image push, kubectl write, Vertex call, or
  secret read was run in this step.
- Fresh verification passed: PowerShell AST parse for all repository
  PowerShell scripts, `terraform.exe -chdir=infra/gcp init -backend=false`,
  `terraform.exe -chdir=infra/gcp fmt -recursive -check`,
  `terraform.exe -chdir=infra/gcp validate`, `git diff --check`, and
  `.venv/bin/python scripts/verify_local.py --env-file .env.example
  --skip-compose` with 313 backend tests plus frontend lint/build.
- `python3 scripts/verify_local.py --env-file .env.example --skip-compose`
  initially failed before local backend test dependencies were installed, and
  full compose verification failed because Docker Desktop WSL integration is
  not enabled in this environment.

As of 2026-07-08, Issue #10 added the first GKE workload layer on branch
`codex/issue-10-gke-workloads`:

- Merged PR #18 so the GKE workload manifests and production frontend image
  path are available on `main`, and Issue #10 is closed.
- Added `frontend/Dockerfile.prod` and `frontend/nginx.conf` so the Vite
  frontend can be built into an nginx image that serves static assets and
  proxies `/api` and `/files` to the in-cluster API service.
- Added Kubernetes namespace and service account resources, with the
  `creativeops-app` Kubernetes service account annotated for the app Google
  service account.
- Added a backend runtime ConfigMap from Terraform defaults, plus a GCS FUSE
  persistent volume and claim for `/data/assets`.
- Added Kubernetes deployments for API, worker, dispatcher, and frontend, an
  internal API service, and a frontend `LoadBalancer` service. Replica defaults
  remain `0` until an intentional apply enables live workloads.
- No live GCP apply was run in this step. The first deployed URL is expected in
  the future Issue #12 mock deployment smoke step, after the frontend
  `LoadBalancer` receives an external IP.
- Fresh verification passed: `.\scripts\verify_gcp_terraform.ps1`,
  `npm run build`, `docker build -f frontend/Dockerfile.prod -t
  creativeops-frontend:gke ./frontend`, `docker run --rm --add-host
  creativeops-api:127.0.0.1 creativeops-frontend:gke nginx -t`,
  `git diff --check`, `git diff --cached --check`, and
  `python scripts/verify_local.py`.

As of 2026-07-08, Issue #9 added the GKE platform, registry, and identity
boundary on branch `codex/issue-9-gke-identity-registry`:

- Merged PR #16 so private managed services are available on `main`, and Issue
  #8 is closed.
- Added backend and frontend Artifact Registry Docker repositories.
- Added GKE Standard cluster and managed node pool using the existing VPC,
  subnet, secondary ranges, Workload Identity pool, and GCS FUSE CSI driver.
- Added a custom GKE node service account scoped for Artifact Registry reads,
  logging, and metrics.
- Added an app Google service account scoped for Vertex AI usage and generated
  asset object access through GCS, with Workload Identity mapping for the future
  `creativeops-app` Kubernetes service account.
- Added Kubernetes provider wiring from the created cluster for the next
  workload PR, and outputs for image repositories, cluster credentials command,
  Workload Identity pool, service account names, and managed service names.
- Fresh verification passed: `.\scripts\verify_gcp_terraform.ps1`,
  `git diff --check`, and `python scripts/verify_local.py`.

As of 2026-07-08, Issue #8 added the private GCP managed services layer on
branch `codex/issue-8-gcp-managed-services`:

- Merged PR #15 so the GCP Terraform foundation is available on `main`, and
  Issue #7 is closed.
- Added VPC, regional GKE subnet, secondary pod/service CIDRs, private service
  access reserved range, and service networking connection.
- Added private Cloud SQL PostgreSQL with public IPv4 disabled, app database
  metadata, and deletion protection controlled by `db_deletion_protection`.
- Added Memorystore Redis with private service access and connected the
  Terraform runtime defaults to `CELERY_BROKER_URL`.
- Added the generated asset Cloud Storage bucket with uniform bucket-level
  access, enforced public access prevention, versioning, and a 30-day lifecycle
  cleanup rule.
- Added only the Secret Manager metadata container for `DATABASE_URL`; no secret
  version, DB password, `.env`, service-account JSON, or credential value is
  committed.
- Fresh verification passed: `.\scripts\verify_gcp_terraform.ps1`,
  `git diff --check`, and `python scripts/verify_local.py`.

As of 2026-07-08, Issue #7 added the first GCP Terraform foundation on branch
`codex/issue-7-gcp-terraform-foundation`:

- Merged PR #6 so GitHub issue/PR templates and Terraform validation workflow
  are available on `main`.
- Merged PR #4 so the GCP deployment plan and child issue execution map are
  available on `main`. Issue #3 remains open as the umbrella for #7 through #14.
- Added the minimal self-validating GCP Terraform stack under `infra/gcp/`:
  provider/version lock, GCS backend placeholder/example, project/region/zone
  variables, safe replica defaults, shared names/labels, runtime defaults that
  do not reference future resources, and required Google API resources.
- Added `scripts/verify_gcp_terraform.ps1` for local
  `terraform init -backend=false`, `terraform fmt -recursive -check`, and
  `terraform validate`.
- Fresh verification passed: `.\scripts\verify_gcp_terraform.ps1`.

As of 2026-07-08, the GCP GKE deployment planning work started on Issue #3:

- Created GitHub Issue #3 for the GCP GKE Terraform deployment path and switched
  to branch `codex/issue-3-gcp-gke-terraform`.
- Added the implementation plan at
  `docs/superpowers/plans/2026-07-08-gcp-gke-terraform.md`. The plan chooses a
  GKE-first stack with Artifact Registry, Cloud SQL PostgreSQL, Memorystore
  Redis, Secret Manager metadata, Cloud Storage FUSE for `/data/assets`, and
  GKE workloads for frontend, API, worker, and dispatcher.
- Added the deployment execution plan at
  `infra/gcp/docs/deployment-plan.md`. This is the operator-facing checklist
  for GCP project bootstrap, Terraform state, Artifact Registry, mock GKE
  deployment, Vertex readiness, evidence capture, and teardown.
- Split the GCP deployment path into child issues under umbrella Issue #3 so
  each meaningful unit can use its own branch, draft PR, review, and merge:
  #7 Terraform foundation, #8 managed data/assets, #9 GKE identity/registry,
  #10 GKE workloads, #11 deployment scripts/runbooks, #12 mock deployment
  smoke, #13 Vertex readiness, and #14 cost-control/teardown evidence.
- Recorded the repository workflow preference in `AGENTS.md`: implementation
  work starts from a GitHub Issue, uses a `codex/issue-*` branch, and ends with
  a draft PR to `main`.
- Fresh verification passed: `git diff --check` and `python scripts/verify_local.py`.
- Fresh verification after adding `infra/gcp/docs/deployment-plan.md` passed:
  plan placeholder scan, `git diff --check`, and `python scripts/verify_local.py`.
- Fresh verification after splitting the GCP deployment queue into child issues
  passed: `git diff --check` and `python scripts/verify_local.py`.

As of 2026-07-08, GitHub collaboration templates and automation were added on
Issue #5:

- Added issue forms modeled after `SKYAHO/Autoresearch` but tailored for
  CreativeOps Studio: feature, bug, infra/Terraform, and ops/QA forms.
- Added a PR template with issue linkage, validation, provider-mode,
  Terraform/deployment impact, and secret-safety checks.
- Added CODEOWNERS for lightweight repo ownership hints.
- Kept collaboration management to GitHub Issues and Pull Requests only; no
  GitHub Project sync workflow is used.
- Added Terraform GitHub Actions automation that runs static `fmt`, `init
  -backend=false`, and `validate` checks for Terraform stack changes.
- Created repository labels used by the templates: `feature`, `infra`,
  `terraform`, `ops`, and `qa`.
- Fresh verification passed: `.github` YAML parse check, `git diff --check`,
  and `python scripts/verify_local.py`.

As of 2026-06-19, the AWS portfolio deployment was intentionally removed:

- Fast-forwarded local `main` to `origin/main` at `727fccb`.
- Initialized Terraform against the existing S3 remote state in
  `ap-southeast-2` and generated a destroy plan for the deployed portfolio
  stack.
- Emptied the frontend S3 bucket and ECR repository images that would otherwise
  block Terraform deletion.
- Applied Terraform destroy for the CloudFront, ALB, ECS API/worker/dispatcher,
  RDS PostgreSQL, ElastiCache Redis, EFS, ECR, frontend S3, VPC/networking,
  CloudWatch Logs, IAM roles, and app Secrets Manager resources.
- Forced deletion without recovery for the two app-managed Secrets Manager
  secrets after Terraform scheduled them for deletion; the RDS managed secret
  was already gone.
- Deleted the manual Terraform backend S3 bucket
  `creativeops-terraform-state-827913617635` after removing its versioned state
  objects and delete markers.
- Verification confirmed Terraform state was empty before backend bucket
  removal, a new destroy plan had no remaining objects, and representative AWS
  resources returned NotFound responses.

As of 2026-06-14, the local frontend UI was aligned with the CreativeOps
Studio direction while keeping backend/API contracts unchanged:

- Switched the local Docker runtime back from Vertex live QA to the default
  mock provider. Local `.env` has `AI_PROVIDER=mock` and empty Google
  credential mount variables. `docker compose up -d --force-recreate backend
  worker dispatcher` was run without `docker-compose.vertex.yml`.
- Verified local `/api/health` through the Vite proxy reports
  `vertex.status=mock_provider`, and backend no longer has the `/secrets/sa.json`
  mount.
- Added AGENTS guidance clarifying that mock and Vertex modes use the same
  backend/worker image; Vertex live QA requires the
  `docker-compose.vertex.yml` override for credential mounting.
- Updated `/generate` to the CreativeOps screenshot-style workspace with
  sidebar/topbar, mode tabs, cinema stage, and bottom composer.
- Updated `/history`, `/ops`, `/jobs/:jobId`, and `/pipelines/:pipelineId`
  with CreativeOps-style hero/status surfaces and darker production dashboard
  panels while preserving existing React Query hooks and API payloads.
- Fresh verification passed: `npm run lint`, `npm run build`, protected
  backend/API diff guard, `/api/health`, `/api/ops/health`, and browser checks
  for `/history`, `/ops`, and a real `/jobs/:jobId` route. Browser console only
  showed React Router future warnings during the clean route check.

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
- Drafted the Phase 5A AWS Terraform deployment runbook. It captures the target
  AWS architecture, Terraform file layout, ECS environment contract, preflight
  blockers, deployment commands, and smoke checks.
- Implemented the Phase 5B AWS Terraform skeleton under `infra/aws/` and
  verified it with `terraform init -backend=false`, `terraform fmt -recursive`,
  `terraform validate`, and a no-apply `terraform plan -refresh=false` using
  AWS account `827913617635`. The plan currently proposes 53 resources.
- Completed the first AWS mock deployment in Sydney (`ap-southeast-2`). The run
  created the Terraform S3 backend bucket, initialized remote state, applied the
  infrastructure, populated the `DATABASE_URL` secret from the RDS managed
  secret, built and pushed the backend image to ECR, uploaded the Vite frontend
  to S3, and invalidated CloudFront.
- Enabled the ECS API, worker, and dispatcher services at desired count `1`.
  Verified CloudFront root `200`, `/api/health` with `ok: true` and DB `up`,
  `/api/ops/health` with job/outbox counts, CloudFront status `Deployed`, and
  ECS services `Desired 1 / Running 1 / Pending 0`.
- During the first AWS apply, the IAM user `de-ai-21` was missing deployment
  permissions for ECS, ELBv2, EFS tagging, and ElastiCache. Added the inline
  IAM policy `CreativeOpsPortfolioDeployPolicy` to that user so Terraform can
  manage the deployed stack.
- Switched the AWS ECS API, worker, and dispatcher services from
  `AI_PROVIDER=mock` to `AI_PROVIDER=vertex`. The service-account JSON was
  stored in AWS Secrets Manager as `GOOGLE_APPLICATION_CREDENTIALS_JSON`
  without printing the secret value, and CloudFront `/api/health` now reports
  `vertex.status=ready`.
- Verified a live app-level Gemini prompt enhancement through CloudFront using
  `gemini-2.5-flash`; the request succeeded with prompt enhancement id
  `ac755727-42d0-465b-b560-f3a53984b911`.
- Pruned completed Phase 1-3 implementation plans and closeout documents so
  agents no longer spend time reading stale migration history.

## Next Suggested Work

- Review and merge the Issue #61 evaluation artifact schema PR, then implement
  Issues #62 through #64 in order to complete the full no-cost mock evaluation
  flow.
- After the mock gate passes, implement Issue #65 for isolated local
  VQAScore/ImageReward/TIFA adapters. Do not start Issue #66 until the user
  explicitly approves the bounded Vertex pilot and its request/image caps.
- Review the Issue #49 managed Prometheus and alert-policy draft PR after
  GitHub checks pass, then merge it into `main`.
- The live GCP stack is currently in temporary demo pause mode: app replicas
  `0`, node pool `0`, and `ai_provider=mock`. Before live autoscaling, HPA, or
  provider failure evidence, intentionally scale the stack back up with the
  personal GCP guard.
- After Issue #49 merges, use a dedicated live observability rollout issue:
  resume the proven mock baseline, build and deploy the new backend image,
  review a Terraform plan with alerts disabled, verify `PodMonitoring` scrape
  ingestion in Cloud Monitoring, then explicitly enable the two alert policies.
- Follow that with a bounded prompt-enhancement provider failure validation
  run: use low-rate Vertex prompt traffic, verify both
  `/api/ops/metrics.provider_failures.by_code` and the managed Prometheus
  provider-failure series, and keep public error/log safety intact. This can
  incur Vertex cost and must use the personal GCP guard.
- Issue #3 remains the umbrella for the GCP GKE Terraform deployment path. Most
  child deployment issues through Vertex readiness are complete; keep future GCP
  work one issue and one branch at a time.
- Use `scripts/setup_local.ps1` after switching machines or after a fresh clone.
  Pass `-RunVerify` when local Python/Node dependencies are installed and you
  want the full quality gate. Pass `-Force` only when intentionally regenerating
  `.env` from `.env.example`.
- If an older local `.env` already exists, make sure it includes the current
  rate-limit keys, provider retry keys, `CELERY_WORKER_CONCURRENCY=2`,
  `CELERY_TASK_ACKS_LATE=true`, `CELERY_TASK_REJECT_ON_WORKER_LOST=true`, and
  `CELERY_WORKER_PREFETCH_MULTIPLIER=1`; `setup_local.ps1` does not overwrite
  existing local `.env` files unless `-Force` is used.
- No AWS portfolio stack is currently live. Before a future AWS redeploy,
  recreate the Terraform backend bucket, run `terraform init` with the backend
  config, and reapply from `infra/aws/`.
- If AWS will not be used again soon, optionally remove the manual IAM inline
  policy `CreativeOpsPortfolioDeployPolicy` from the `de-ai-21` IAM user after
  confirming that user does not need those deployment permissions.
- For a future portfolio showing, recreate the AWS stack first, then consider
  custom domain plus ACM certificate, CloudFront HTTPS alias, and a small
  deployment script that repeats build, ECR push, S3 sync, invalidation, and
  service update.
- Run the full local quality gate before committing documentation changes:

```powershell
python scripts/verify_local.py
```

## Verification Log

Latest Vertex API smoke:

```powershell
# 2026-06-13, local gcloud token only; no credential value was printed.
# Project: krafton-vertex-live-3108
# Location: us-central1
# Model: gemini-2.5-flash
# Result: HTTP 200 from generateContent
```

Previous AWS Vertex deployment checks:

```powershell
# 2026-06-13, AWS account 827913617635, ap-southeast-2
# Backend image: creativeops-portfolio-backend:portfolio
# Digest: sha256:dfe98b5f780986f5756f921d55250e26a3269f450e03a8917c37ea4313c391e5
# ECS task definitions: api/worker/dispatcher revision 3, desired 1/running 1
Invoke-RestMethod -Uri "https://d3up7fakknt15b.cloudfront.net/api/health"
Invoke-RestMethod -Uri "https://d3up7fakknt15b.cloudfront.net/api/ops/health"
aws ecs describe-services --cluster creativeops-portfolio --services creativeops-portfolio-api creativeops-portfolio-worker creativeops-portfolio-dispatcher --region ap-southeast-2
Invoke-RestMethod -Method Post `
  -Uri "https://d3up7fakknt15b.cloudfront.net/api/prompts/enhance" `
  -ContentType "application/json" `
  -Body '{"prompt":"small blue cup on desk","target_mode":"t2i","target_model":"imagen-4.0-fast-generate-001","creativity_preset":"faithful"}'
git diff --check
python scripts/verify_local.py
```

Expected:

- no whitespace errors
- ECR has the `portfolio` image tag
- CloudFront root and API health checks return success
- CloudFront `/api/health` reports `vertex.status=ready`
- Prompt enhancement returns a Gemini result through the deployed API
- ECS API, worker, and dispatcher are all running
- full local quality gate passes when local dependencies are available

Latest AWS teardown checks:

```powershell
# 2026-06-19, AWS account 827913617635, ap-southeast-2
terraform init -backend-config="bucket=creativeops-terraform-state-827913617635" -backend-config="key=creativeops/portfolio/terraform.tfstate" -backend-config="region=ap-southeast-2" -backend-config="encrypt=true" -backend-config="use_lockfile=true"
terraform plan -destroy '-var=container_image=827913617635.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-portfolio-backend:portfolio' '-out=tfplan.destroy'
terraform apply -auto-approve tfplan.destroy
terraform destroy -auto-approve '-var=container_image=827913617635.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-portfolio-backend:portfolio'
terraform state list
terraform plan -destroy '-var=container_image=827913617635.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-portfolio-backend:portfolio' -detailed-exitcode
aws rds describe-db-instances --db-instance-identifier creativeops-portfolio --region ap-southeast-2
aws elasticache describe-replication-groups --replication-group-id creativeops-portfolio-redis --region ap-southeast-2
aws cloudfront get-distribution --id E2F32KLJZ6RUUM
aws ecr describe-repositories --repository-names creativeops-portfolio-backend --region ap-southeast-2
aws s3api head-bucket --bucket creativeops-portfolio-frontend-827913617635 --region ap-southeast-2
aws s3api head-bucket --bucket creativeops-terraform-state-827913617635 --region ap-southeast-2
aws logs describe-log-groups --log-group-name-prefix /creativeops/portfolio --region ap-southeast-2
```

Expected:

- Terraform state is empty before backend bucket deletion.
- Fresh Terraform destroy plan reports no objects need to be destroyed.
- RDS, ElastiCache, CloudFront, ECR, frontend S3, EFS, VPC, and ALB checks
  return NotFound responses.
- S3 bucket listing has no `creativeops-` buckets.
- CloudWatch log group prefix returns an empty list.
- The Terraform backend bucket is deleted after state verification.
- `tag:GetResources` verification was attempted but the current IAM user lacks
  `tag:GetResources`; individual resource checks were used instead.
