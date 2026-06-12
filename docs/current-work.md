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
- AWS portfolio deployment: the mock-mode stack is deployed in Sydney,
  `ap-southeast-2`, under AWS account `827913617635`. CloudFront serves the
  frontend at `https://d3up7fakknt15b.cloudfront.net`, proxies `/api/*` and
  `/files/*` to the ALB, and all three ECS services are enabled with desired
  count `1`.
- AWS Terraform: `infra/aws/` contains the Terraform baseline for the deployed
  portfolio stack. The committed defaults keep ECS desired counts at `0`; use
  local ignored tfvars when intentionally enabling the live services.
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
- Monitor AWS cost while the portfolio stack is live. If the demo is not needed,
  scale ECS desired counts back to `0` or destroy the stack intentionally with
  Terraform.
- Safe AWS Vertex credential injection is now implemented through
  `GOOGLE_APPLICATION_CREDENTIALS_JSON` from Secrets Manager. Next, add the real
  service-account JSON value to the existing AWS secret, apply with
  `AI_PROVIDER=vertex`, and run the smallest Gemini smoke test before any
  Imagen/Veo request.
- Optional polish before showing the portfolio: custom domain plus ACM
  certificate, CloudFront HTTPS alias, and a small deployment script that
  repeats build, ECR push, S3 sync, invalidation, and service update.
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

Latest AWS deployment checks:

```powershell
cd infra/aws; terraform init -reconfigure "-backend-config=backend.hcl"
cd infra/aws; terraform fmt -recursive -check
cd infra/aws; terraform validate
$cfDomain = terraform output -raw cloudfront_domain_name
$tfvars = Join-Path $env:TEMP "creativeops-all-services.tfvars.json"
@{
  container_image = "827913617635.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-portfolio-backend:portfolio"
  api_desired_count = 1
  worker_desired_count = 1
  dispatcher_desired_count = 1
  cors_origins = @("https://$cfDomain")
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $tfvars -Encoding ascii
terraform plan -input=false "-var-file=$tfvars"
aws ecr describe-images --repository-name creativeops-portfolio-backend --image-ids imageTag=portfolio --region ap-southeast-2
Invoke-RestMethod -Uri "https://d3up7fakknt15b.cloudfront.net/api/health"
Invoke-RestMethod -Uri "https://d3up7fakknt15b.cloudfront.net/api/ops/health"
aws ecs describe-services --cluster creativeops-portfolio --services creativeops-portfolio-api creativeops-portfolio-worker creativeops-portfolio-dispatcher --region ap-southeast-2
git diff --check
python scripts/verify_local.py
```

Expected:

- no whitespace errors
- Terraform configuration validates
- Terraform can refresh/plan against the deployed stack
- ECR has the `portfolio` image tag
- CloudFront root and API health checks return success
- ECS API, worker, and dispatcher are all running
- full local quality gate passes when local dependencies are available
