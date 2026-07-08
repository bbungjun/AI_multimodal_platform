# GCP GKE Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy CreativeOps Studio to Google Cloud with a GKE-first portfolio architecture, prove the full app flow in `AI_PROVIDER=mock`, then switch to Vertex mode only after no-cost smoke checks pass.

**Architecture:** Terraform creates a GCP stack under `infra/gcp`: Artifact Registry, VPC/private service access, Cloud SQL PostgreSQL, Memorystore Redis, Cloud Storage asset bucket, GKE, Workload Identity, and Kubernetes workloads for frontend, API, worker, and dispatcher. The first live deployment keeps app replicas at `0` until runtime secrets exist, then scales to `1` for mock smoke. Vertex mode uses Workload Identity and ADC; no service-account JSON is committed or mounted.

**Tech Stack:** Terraform 1.10+, Google Cloud SDK, Docker, GKE Standard, Artifact Registry, Cloud SQL PostgreSQL, Memorystore Redis, Cloud Storage FUSE CSI, Kubernetes, FastAPI, Celery, React/Vite, nginx.

---

## Assumptions

- Issue: `#3 Add GCP GKE Terraform deployment path`
- Branch: `codex/issue-3-gcp-gke-terraform`
- Terraform stack path: `infra/gcp`
- Default GCP region: `asia-northeast3`
- Default GKE zone: `asia-northeast3-a`
- Vertex location: `us-central1`
- First deployment mode: `AI_PROVIDER=mock`
- Runtime namespace: `creativeops-portfolio`
- Runtime secret name: `creativeops-runtime-secrets`
- State bucket name pattern: `creativeops-terraform-state-$env:GCP_PROJECT_ID`

Do not print, commit, or paste `.env`, service-account JSON, ADC files, API keys,
private keys, DB passwords, `backend.hcl`, `.tfvars`, Terraform state, generated
media, or runtime logs containing secrets.

## Issue And PR Execution Map

Use Issue #3 as the umbrella for the GCP deployment path. Implementation work
must happen in the child issues below, one issue at a time, with a fresh branch,
draft PR, review, and merge before the next issue starts.

Preparation order:

1. Review and merge PR #6 so issue/PR templates and Terraform validation
   workflow are available on `main`.
2. Review and merge PR #4 so this GCP deployment plan is available on `main`.
3. Start Issue #7 from the updated `main` branch.

Per-issue workflow:

1. `git switch main`
2. `git pull --ff-only origin main`
3. `git switch -c codex/issue-<issue-number>-<short-slug>`
4. Implement only the issue scope and update `docs/current-work.md`.
5. Run the issue acceptance checks plus `git diff --check`.
6. Push the branch and open a draft PR to `main`.
7. Review the PR, address feedback, and merge before starting the next issue.

| Order | Issue | Branch | Merge gate |
| --- | --- | --- | --- |
| 1 | #7 `[INFRA] Add GCP Terraform foundation and validation` | `codex/issue-7-gcp-terraform-foundation` | Terraform provider/API/variable foundation validates with no live apply. |
| 2 | #8 `[INFRA] Add GCP managed data and asset services` | `codex/issue-8-gcp-managed-services` | Cloud SQL, Redis, VPC/private access, GCS, and secret metadata validate without committed secret values. |
| 3 | #9 `[INFRA] Add GKE, IAM, Workload Identity, and Artifact Registry` | `codex/issue-9-gke-identity-registry` | GKE, Artifact Registry, IAM, and Workload Identity validate without service-account key files. |
| 4 | #10 `[INFRA] Add production frontend image and GKE workload manifests` | `codex/issue-10-gke-workloads` | Frontend image and GKE workloads validate with safe replica defaults. |
| 5 | #11 `[OPS] Add GCP image, secret bootstrap, and deployment runbooks` | `codex/issue-11-gcp-deployment-runbooks` | Build/push and secret bootstrap scripts plus runbooks are reviewed and secret-safe. |
| 6 | #12 `[QA] Execute GCP mock deployment and smoke validation` | `codex/issue-12-gcp-mock-smoke` | Live GCP mock deployment passes health, ops health, and mock golden-path smoke. |
| 7 | #13 `[QA] Verify GCP Vertex readiness through Workload Identity` | `codex/issue-13-gcp-vertex-readiness` | Vertex readiness passes through Workload Identity; any Gemini smoke is explicitly cost-approved. |
| 8 | #14 `[OPS] Add GCP cost-control and teardown evidence` | `codex/issue-14-gcp-cost-control` | Scale-down or teardown evidence proves no unexpected billable runtime resources remain. |

## Phase 0: Local And GitHub Preconditions

- [ ] **Step 1: Confirm branch and clean state**

Run:

```powershell
git switch codex/issue-3-gcp-gke-terraform
git status --short --branch
git diff --cached --name-only
```

Expected:

```text
## codex/issue-3-gcp-gke-terraform...origin/codex/issue-3-gcp-gke-terraform
```

`git diff --cached --name-only` prints no files.

- [ ] **Step 2: Confirm local CLIs**

Run:

```powershell
terraform version
gcloud version
docker version
kubectl version --client
```

Expected:

```text
Each command exits with code 0.
```

- [ ] **Step 3: Set deployment variables in the current shell**

Run:

```powershell
$env:GCP_PROJECT_ID = Read-Host "GCP project id"
$env:GCP_REGION = "asia-northeast3"
$env:GCP_ZONE = "asia-northeast3-a"
$env:IMAGE_TAG = "portfolio"
$env:TF_VAR_gcp_project_id = $env:GCP_PROJECT_ID
```

Expected:

```text
Variables are set only in the local shell. Do not commit them to files.
```

## Phase 1: GCP Project And Remote State Bootstrap

- [ ] **Step 1: Select the GCP project**

Run:

```powershell
gcloud auth login
gcloud config set project $env:GCP_PROJECT_ID
gcloud projects describe $env:GCP_PROJECT_ID --format="value(projectId)"
```

Expected:

```text
The command prints the same project id as $env:GCP_PROJECT_ID.
```

- [ ] **Step 2: Enable the minimum bootstrap APIs**

Run:

```powershell
gcloud services enable `
  cloudresourcemanager.googleapis.com `
  serviceusage.googleapis.com `
  storage.googleapis.com `
  artifactregistry.googleapis.com `
  --project $env:GCP_PROJECT_ID
```

Expected:

```text
Command exits with code 0.
```

- [ ] **Step 3: Create the Terraform state bucket**

Run:

```powershell
$stateBucket = "creativeops-terraform-state-$env:GCP_PROJECT_ID"
gcloud storage buckets create "gs://$stateBucket" `
  --project $env:GCP_PROJECT_ID `
  --location $env:GCP_REGION `
  --uniform-bucket-level-access
gcloud storage buckets update "gs://$stateBucket" --versioning
```

Expected:

```text
The bucket exists and versioning is enabled.
```

- [ ] **Step 4: Create local backend config outside Git**

Run:

```powershell
@"
bucket = "$stateBucket"
prefix = "creativeops/portfolio/gcp"
"@ | Set-Content -Path infra/gcp/backend.hcl -Encoding UTF8
git status --short --ignored infra/gcp/backend.hcl
```

Expected:

```text
!! infra/gcp/backend.hcl
```

`backend.hcl` must stay ignored.

## Phase 2: Terraform Static Validation

- [ ] **Step 1: Initialize with remote state**

Run:

```powershell
terraform -chdir=infra/gcp init -backend-config=backend.hcl
```

Expected:

```text
Terraform has been successfully initialized!
```

- [ ] **Step 2: Run static checks**

Run:

```powershell
terraform -chdir=infra/gcp fmt -recursive -check
terraform -chdir=infra/gcp validate
```

Expected:

```text
Success! The configuration is valid.
```

## Phase 3: Artifact Registry Bootstrap

- [ ] **Step 1: Define image URIs**

Run:

```powershell
$backendImage = "$env:GCP_REGION-docker.pkg.dev/$env:GCP_PROJECT_ID/creativeops-portfolio-backend/creativeops-backend:$env:IMAGE_TAG"
$frontendImage = "$env:GCP_REGION-docker.pkg.dev/$env:GCP_PROJECT_ID/creativeops-portfolio-frontend/creativeops-frontend:$env:IMAGE_TAG"
$backendImage
$frontendImage
```

Expected:

```text
Two Artifact Registry image URIs are printed. They contain no secrets.
```

- [ ] **Step 2: Apply only API and Artifact Registry resources**

Run:

```powershell
terraform -chdir=infra/gcp apply `
  -target=google_project_service.required `
  -target=google_artifact_registry_repository.backend `
  -target=google_artifact_registry_repository.frontend `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage"
```

Expected:

```text
Artifact Registry repositories exist for backend and frontend images.
```

- [ ] **Step 3: Build and push images**

Run:

```powershell
gcloud auth configure-docker "$env:GCP_REGION-docker.pkg.dev" --quiet
docker build -t $backendImage ./backend
docker push $backendImage
docker build -f frontend/Dockerfile.prod -t $frontendImage ./frontend
docker push $frontendImage
```

Expected:

```text
Both image pushes finish successfully.
```

## Phase 4: Infrastructure Apply With Replicas At Zero

- [ ] **Step 1: Apply cloud infrastructure and Kubernetes objects without starting pods**

Run:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=0" `
  -var "frontend_replicas=0" `
  -var "worker_replicas=0" `
  -var "dispatcher_replicas=0" `
  -var "ai_provider=mock"
```

Expected:

```text
Terraform creates VPC, private service access, Cloud SQL, Memorystore, GCS asset bucket, GKE, IAM, and Kubernetes manifests.
```

- [ ] **Step 2: Connect kubectl to the cluster**

Run:

```powershell
gcloud container clusters get-credentials creativeops-portfolio `
  --zone $env:GCP_ZONE `
  --project $env:GCP_PROJECT_ID
kubectl get namespace creativeops-portfolio
```

Expected:

```text
The creativeops-portfolio namespace is listed.
```

## Phase 5: Runtime Secret Bootstrap

- [ ] **Step 1: Create or rotate the Cloud SQL app user and runtime secret**

Run:

```powershell
.\scripts\bootstrap_gcp_runtime_secrets.ps1 `
  -ProjectId $env:GCP_PROJECT_ID `
  -Region $env:GCP_REGION `
  -Zone $env:GCP_ZONE `
  -Environment "portfolio" `
  -DbUser "app" `
  -DbName "multimodal"
```

Expected:

```text
The script reports that the runtime secret was refreshed in namespace creativeops-portfolio.
```

- [ ] **Step 2: Confirm the Kubernetes secret exists without printing values**

Run:

```powershell
kubectl get secret creativeops-runtime-secrets -n creativeops-portfolio
```

Expected:

```text
The secret exists. Do not run commands that print the secret value.
```

## Phase 6: Mock Mode Scale-Up And Smoke

- [ ] **Step 1: Scale app workloads to one replica**

Run:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=1" `
  -var "frontend_replicas=1" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "ai_provider=mock"
```

Expected:

```text
Terraform updates deployments to one replica each.
```

- [ ] **Step 2: Wait for rollouts**

Run:

```powershell
kubectl rollout status deployment/creativeops-api -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-worker -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-dispatcher -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-frontend -n creativeops-portfolio --timeout=180s
```

Expected:

```text
Each deployment successfully rolls out.
```

- [ ] **Step 3: Find the frontend endpoint**

Run:

```powershell
$frontendIp = kubectl get svc creativeops-frontend `
  -n creativeops-portfolio `
  -o jsonpath="{.status.loadBalancer.ingress[0].ip}"
$frontendUrl = "http://$frontendIp"
$frontendUrl
```

Expected:

```text
The command prints an http URL with an external IP.
```

- [ ] **Step 4: Check health through the frontend proxy**

Run:

```powershell
Invoke-RestMethod -Uri "$frontendUrl/api/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/health"
```

Expected:

```text
Health is ok, DB is up, and vertex.status is mock_provider.
```

- [ ] **Step 5: Run mock golden-path smoke**

Run:

```powershell
python scripts/smoke_mock_golden_path.py --base-url $frontendUrl --timeout-sec 120
```

Expected:

```text
SMOKE PASSED
```

## Phase 7: Vertex Mode Readiness

- [ ] **Step 1: Confirm mock smoke evidence before Vertex**

Run:

```powershell
git status --short --branch
```

Expected:

```text
Working tree is clean except ignored local deployment files.
```

Continue only if Phase 6 passed. Vertex checks can create billable provider
requests after readiness.

- [ ] **Step 2: Switch provider mode to Vertex**

Run:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=1" `
  -var "frontend_replicas=1" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "ai_provider=vertex"
```

Expected:

```text
Deployments roll with AI_PROVIDER=vertex.
```

- [ ] **Step 3: Verify Vertex readiness without generation**

Run:

```powershell
kubectl rollout status deployment/creativeops-api -n creativeops-portfolio --timeout=180s
Invoke-RestMethod -Uri "$frontendUrl/api/health"
```

Expected:

```text
vertex.ready is true and vertex.status is ready.
```

- [ ] **Step 4: Run one Gemini prompt enhancement only after cost confirmation**

Run:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "$frontendUrl/api/prompts/enhance" `
  -ContentType "application/json" `
  -Body '{"prompt":"small blue cup on desk","target_mode":"t2i","target_model":"imagen-4.0-fast-generate-001","creativity_preset":"faithful"}'
```

Expected:

```text
The response contains a prompt enhancement id and edited prompt draft.
```

Do not run Imagen or Veo live generation in this phase unless a separate QA
issue explicitly accepts the cost.

## Phase 8: Portfolio Evidence

- [ ] **Step 1: Record public evidence only**

Add a short note to `docs/current-work.md` with:

```markdown
- GCP GKE mock deployment endpoint returned `/api/health` ok, DB up, and
  `vertex.status=mock_provider`.
- Mock golden-path smoke completed with generated asset streaming through
  `/files/...`.
- Vertex readiness returned `vertex.status=ready` after Workload Identity
  switch.
```

Do not include prompts with private content, credentials, `.env` values, DB
passwords, service-account JSON, or raw logs containing environment values.

- [ ] **Step 2: Commit documentation evidence**

Run:

```powershell
git add docs/current-work.md
git commit -m "docs: record gcp gke deployment evidence"
```

Expected:

```text
Commit succeeds with documentation only.
```

## Phase 9: Cost Control And Teardown

- [ ] **Step 1: Scale down when the demo is not needed**

Run:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=0" `
  -var "frontend_replicas=0" `
  -var "worker_replicas=0" `
  -var "dispatcher_replicas=0" `
  -var "ai_provider=mock"
```

Expected:

```text
GKE workloads are scaled to zero. Managed services may still incur cost.
```

- [ ] **Step 2: Destroy the stack when portfolio QA is complete**

Run:

```powershell
terraform -chdir=infra/gcp destroy `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "ai_provider=mock"
```

Expected:

```text
Terraform destroys managed resources. Confirm manually that no unexpected GCP resources remain.
```

## Review Checklist

- `infra/aws/` stays untouched.
- First deployment uses `AI_PROVIDER=mock`.
- Runtime secrets are created after infrastructure and never committed.
- Workloads start only after `DATABASE_URL` exists.
- `/data/assets` remains the app-facing storage path.
- GKE Workload Identity is used for Vertex readiness.
- Imagen/Veo live generation is not run without a separate cost-aware QA issue.
- Terraform state, `backend.hcl`, `.tfvars`, and generated media remain ignored.

## Self-Review

- Spec coverage: project bootstrap, remote state, Artifact Registry, image push, full apply, secret bootstrap, mock smoke, Vertex readiness, evidence, and teardown are all covered.
- Placeholder scan: commands use shell variables set in Phase 0 instead of committed project IDs or secrets.
- Type consistency: namespace, deployment names, image variables, and secret names match the planned Terraform/Kubernetes naming.
- Scope check: this plan documents deployment execution only. Terraform source implementation remains in the broader `docs/superpowers/plans/2026-07-08-gcp-gke-terraform.md` plan.
