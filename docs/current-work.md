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

## Last Completed Work

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

- Review and merge the Issue #8 PR after checks pass. Then start Issue #9 from
  updated `main` using branch `codex/issue-9-gke-identity-registry`.
- Continue one child issue at a time through #14, always branching from updated
  `main`, opening a draft PR, getting review, and merging before the next issue
  starts.
- Issue #3 remains the umbrella for the GCP GKE Terraform deployment path. The
  implementation plan lives at
  `docs/superpowers/plans/2026-07-08-gcp-gke-terraform.md`; the deployment
  execution checklist and issue map live at `infra/gcp/docs/deployment-plan.md`.
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
