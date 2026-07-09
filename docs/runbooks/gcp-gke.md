# GCP GKE Deployment Runbook

Use this runbook to deploy CreativeOps Studio to the personal GCP project in
`AI_PROVIDER=mock` first. Do not use team GCP accounts or projects for this
repository.

## Safety Preconditions

- Personal account: `youngjun3108@gmail.com`
- Personal project: `krafton-vertex-live-3108`
- Blocked team account: `sk.yaho2026@gmail.com`
- Blocked team project: `ar-infra-501607`
- Do not print `.env`, ADC files, service-account JSON, API keys, private keys,
  DB passwords, Terraform state, `backend.hcl`, `.tfvars`, or Kubernetes Secret
  payloads.

Start every GCP deployment shell with:

```powershell
.\scripts\use_personal_gcp.ps1
gcloud config get-value account
gcloud config get-value project
```

Expected:

```text
youngjun3108@gmail.com
krafton-vertex-live-3108
```

Do not run `terraform apply`, `kubectl`, or GCP write commands until this check
matches.

When running from WSL bash, use the same personal config boundary with bash
syntax before any GCP command:

```bash
export CLOUDSDK_CONFIG="$HOME/.gcloud-creativeops-personal"
export KUBECONFIG="$HOME/.kube/creativeops-personal"
unset GOOGLE_APPLICATION_CREDENTIALS
unset GOOGLE_APPLICATION_CREDENTIALS_HOST
export GOOGLE_CLOUD_PROJECT="krafton-vertex-live-3108"
export CLOUDSDK_CORE_PROJECT="krafton-vertex-live-3108"
export TF_VAR_gcp_project_id="krafton-vertex-live-3108"
gcloud config get-value account
gcloud config get-value project
```

In WSL, prefer a Linux Terraform binary for the GCS backend. Windows
`terraform.exe` can fail while writing the backend lock from a WSL filesystem.
If Terraform reports that default credentials are missing, run a personal user
ADC login in the guarded shell; do not use or mount service-account JSON files
for this repo deployment.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_PROJECT"
```

## Local Variables

The personal guard script sets these defaults:

```powershell
$env:GCP_PROJECT_ID
$env:GCP_REGION
$env:GCP_ZONE
$env:IMAGE_TAG
$env:TF_VAR_gcp_project_id
```

Override only in the current shell when intentionally changing a deployment
dimension:

```powershell
$env:IMAGE_TAG = git rev-parse --short HEAD
```

## Remote State Bootstrap

Enable only the APIs needed to create the state bucket:

```powershell
gcloud services enable `
  cloudresourcemanager.googleapis.com `
  serviceusage.googleapis.com `
  storage.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  --project $env:GCP_PROJECT_ID
```

Create the ignored Terraform backend config:

```powershell
$stateBucket = "creativeops-terraform-state-$env:GCP_PROJECT_ID"
gcloud storage buckets create "gs://$stateBucket" `
  --project $env:GCP_PROJECT_ID `
  --location $env:GCP_REGION `
  --uniform-bucket-level-access
gcloud storage buckets update "gs://$stateBucket" --versioning

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

## Terraform Init And Static Checks

```powershell
terraform -chdir=infra/gcp init -backend-config=backend.hcl
terraform -chdir=infra/gcp fmt -recursive -check
terraform -chdir=infra/gcp validate
```

## Artifact Registry And Images

Define image URIs:

```powershell
$backendImage = "$env:GCP_REGION-docker.pkg.dev/$env:GCP_PROJECT_ID/creativeops-portfolio-backend/creativeops-backend:$env:IMAGE_TAG"
$frontendImage = "$env:GCP_REGION-docker.pkg.dev/$env:GCP_PROJECT_ID/creativeops-portfolio-frontend/creativeops-frontend:$env:IMAGE_TAG"
```

Create APIs and Artifact Registry repositories first:

```powershell
terraform -chdir=infra/gcp apply `
  -target=google_project_service.required `
  -target=google_artifact_registry_repository.backend `
  -target=google_artifact_registry_repository.frontend `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage"
```

Build and push images through the guarded helper:

```powershell
.\scripts\build_push_gcp_images.ps1 -ImageTag $env:IMAGE_TAG
```

The script refuses to run unless the personal GCP account and project are
active.

If Docker Desktop WSL integration is unavailable, use Cloud Build instead:

```powershell
gcloud builds submit ./backend --tag $backendImage --project $env:GCP_PROJECT_ID
gcloud builds submit ./frontend `
  --config infra/gcp/cloudbuild/frontend.yaml `
  --substitutions "_IMAGE=$frontendImage" `
  --project $env:GCP_PROJECT_ID
```

## Apply Infrastructure With Replicas At Zero

Keep all app replicas at `0` until the runtime secret exists:

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

Connect kubectl to the personal cluster:

```powershell
gcloud container clusters get-credentials creativeops-portfolio `
  --zone $env:GCP_ZONE `
  --project $env:GCP_PROJECT_ID
kubectl get namespace creativeops-portfolio
```

## Runtime Secret Bootstrap

Create or rotate the Cloud SQL app user password and refresh the runtime secret:

```powershell
.\scripts\bootstrap_gcp_runtime_secrets.ps1
kubectl get secret creativeops-runtime-secrets -n creativeops-portfolio
```

The script:

- generates a new DB password without printing it
- creates or rotates the Cloud SQL user through the Cloud SQL Admin API
- adds a new Secret Manager version for the Terraform-owned database URL secret
- applies the Kubernetes `creativeops-runtime-secrets` Secret from a temporary
  file

Do not run `kubectl get secret -o yaml`, `kubectl describe secret`, or any
command that prints Secret payloads.

## Mock Scale-Up And Smoke

Scale the user-facing API and frontend to two replicas when validating rollout
safety. Keep the worker and dispatcher at one replica unless a separate capacity
or HA issue changes the queue-processing design:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=2" `
  -var "frontend_replicas=2" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "node_count=2" `
  -var "ai_provider=mock"
```

Wait for rollouts:

```powershell
kubectl rollout status deployment/creativeops-api -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-worker -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-dispatcher -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-frontend -n creativeops-portfolio --timeout=180s
```

Find the frontend URL and verify health:

```powershell
$frontendIp = kubectl get svc creativeops-frontend `
  -n creativeops-portfolio `
  -o jsonpath="{.status.loadBalancer.ingress[0].ip}"
$frontendUrl = "http://$frontendIp"
Invoke-RestMethod -Uri "$frontendUrl/api/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/metrics"
python scripts/smoke_mock_golden_path.py --base-url $frontendUrl --timeout-sec 120
```

Expected health mode: `vertex.status=mock_provider`.

`/api/ops/metrics` is an application-runtime baseline for the API pod process.
Use it before and after smoke or k6 runs to compare request throughput, error
rate, per-endpoint latency, status counts, and provider failure codes. It does
not print request/response bodies, env values, or Secret payloads.

## Rollout Safety And Rollback

API and frontend deployments use readiness-gated `RollingUpdate` with
`maxUnavailable=0` and `maxSurge=1`. With at least two replicas, Kubernetes
keeps existing ready pods serving while a replacement pod starts and passes its
readiness probe. The API liveness probe uses `/api/health/live`, which checks
only process availability; readiness remains on `/api/health`, which includes
DB and Vertex readiness.

Capacity is part of the rollout contract. When `api_replicas > 1` or
`frontend_replicas > 1`, set `node_count=2` or higher in the same Terraform
plan. Terraform intentionally fails early if a multi-replica user-facing rollout
is planned against a single-node pool, because `maxUnavailable=0` plus
`maxSurge=1` needs room for replacement pods while old pods remain serving. In
the 2026-07-09 live rollout, omitting this left new API and worker pods Pending
with `Insufficient cpu` until the node pool was expanded.

Before changing image tags, runtime config, or prompt-enhancement behavior,
capture the current deployment state and runtime metrics:

```powershell
kubectl get deploy creativeops-api creativeops-frontend `
  -n creativeops-portfolio `
  -o wide
Invoke-RestMethod -Uri "$frontendUrl/api/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/metrics"
```

Apply the image or config change with the intended replica counts, then watch
rollouts and compare runtime metrics:

```powershell
kubectl rollout status deployment/creativeops-api -n creativeops-portfolio --timeout=180s
kubectl rollout status deployment/creativeops-frontend -n creativeops-portfolio --timeout=180s
Invoke-RestMethod -Uri "$frontendUrl/api/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/metrics"
```

For HTTP availability evidence, run the k6 readiness profile during or
immediately after the rollout and record p95/p99 latency, HTTP failure rate,
and any provider failure counters. Use live prompt profiles only when a
cost-aware issue explicitly approves Gemini traffic.

If the rollout fails or `/api/ops/metrics` shows an unexpected error-rate spike,
rollback with one of these paths:

```powershell
kubectl rollout undo deployment/creativeops-api -n creativeops-portfolio
kubectl rollout undo deployment/creativeops-frontend -n creativeops-portfolio
```

or reapply Terraform with the previous backend/frontend image tags. Record the
previous and restored image tags, rollout status, health, and metrics in
`docs/current-work.md`.

Worker and dispatcher rollouts are not user-facing HTTP zero-downtime evidence.
The worker is protected by late ack, reject-on-worker-lost, prefetch `1`, and
Postgres job state, so rollout safety means avoiding lost work and confirming
failed or redelivered jobs are repairable. The dispatcher is kept singleton by
default to avoid overlapping outbox publishers unless a future issue proves a
multi-dispatcher locking strategy.

## Autoscaling Readiness

Do not enable autoscaling on the live stack as a side effect of routine
deployment or pause/resume work. Autoscaling is an explicit operating mode with
separate evidence.

Start from the current cleanup state. If the stack is in temporary demo pause,
first resume the proven rollout baseline with the personal GCP guard:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=2" `
  -var "frontend_replicas=2" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "node_count=2" `
  -var "ai_provider=mock"
```

Before applying autoscaling live, run a no-apply Terraform plan with explicit
autoscaling values and record the intended min/max node counts. Then collect a
baseline with the k6 readiness profile and `/api/ops/metrics`. Autoscaling
should not be considered ready until the evidence includes p95/p99 latency,
HTTP failure rate, Pending pod count, node count before/after, and a rollback
path back to fixed `node_count=2`.

## Workload HPA Readiness

Workload HPA is separate from node pool autoscaling. Node pool autoscaling adds
or removes worker nodes; HPA changes the API and frontend Deployment replica
counts. Do not enable HPA as part of routine deploy, pause, or resume work.
Enable it only for a dedicated evidence issue.

Terraform still declares the initial Deployment replica floor. When HPA is
enabled, set each initial replica count equal to that workload's HPA minimum so
the first apply is predictable and Terraform is not fighting the controller at
the start of the test:

```powershell
terraform -chdir=infra/gcp plan `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=2" `
  -var "api_hpa_enabled=true" `
  -var "api_hpa_min_replicas=2" `
  -var "api_hpa_max_replicas=4" `
  -var "api_hpa_cpu_target_utilization=70" `
  -var "frontend_replicas=2" `
  -var "frontend_hpa_enabled=true" `
  -var "frontend_hpa_min_replicas=2" `
  -var "frontend_hpa_max_replicas=4" `
  -var "frontend_hpa_cpu_target_utilization=70" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "node_count=2" `
  -var "node_pool_autoscaling_enabled=true" `
  -var "node_pool_autoscaling_min_count=1" `
  -var "node_pool_autoscaling_max_count=2" `
  -var "ai_provider=mock"
```

Before applying, confirm the plan only creates or updates the expected HPA
resources and does not alter Secrets, managed data services, or provider mode.
After applying, verify:

```powershell
kubectl get hpa -n creativeops-portfolio
kubectl describe hpa creativeops-api -n creativeops-portfolio
kubectl describe hpa creativeops-frontend -n creativeops-portfolio
kubectl get deploy -n creativeops-portfolio
Invoke-RestMethod -Uri "$frontendUrl/api/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/metrics"
```

For load evidence, run the k6 readiness profile first to capture a no-generation
baseline. A later HPA stress profile should record starting replicas, peak
replicas, node count before/after, Pending pods, p95/p99 latency, HTTP failure
rate, and `/api/ops/metrics` error rate. In active HPA tests, Terraform drift can
temporarily show Deployment replica differences because the HPA controller owns
runtime scale decisions. Record that boundary instead of treating it as a code
drift bug.

Rollback to fixed replicas by applying with HPA disabled and the fixed replica
counts:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=2" `
  -var "api_hpa_enabled=false" `
  -var "frontend_replicas=2" `
  -var "frontend_hpa_enabled=false" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "node_count=2" `
  -var "node_pool_autoscaling_enabled=true" `
  -var "node_pool_autoscaling_min_count=1" `
  -var "node_pool_autoscaling_max_count=2" `
  -var "ai_provider=mock"
```

## Vertex Readiness

Run this only after mock smoke passes. Imagen and Veo live generation remain out
of scope unless a separate cost-aware QA issue approves them.

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=2" `
  -var "frontend_replicas=2" `
  -var "worker_replicas=1" `
  -var "dispatcher_replicas=1" `
  -var "node_count=2" `
  -var "ai_provider=vertex"
Invoke-RestMethod -Uri "$frontendUrl/api/health"
Invoke-RestMethod -Uri "$frontendUrl/api/ops/metrics"
```

Expected readiness mode: `vertex.status=ready`.

Run at most one Gemini prompt-enhancement smoke only after confirming the cost
intent in Issue #13.

## Scale Down Or Destroy

Use **temporary demo pause** when the portfolio environment should remain
recreatable without rebuilding managed data services. This scales app workloads
and the GKE node pool to zero, switches future app pods back to mock mode, and
keeps Terraform-managed platform resources intact:

```powershell
terraform -chdir=infra/gcp apply `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "api_replicas=0" `
  -var "frontend_replicas=0" `
  -var "worker_replicas=0" `
  -var "dispatcher_replicas=0" `
  -var "node_count=0" `
  -var "ai_provider=mock"
```

Expected temporary-pause state:

- GKE app deployments have desired replicas `0`.
- The app namespace has no running API, frontend, worker, or dispatcher pods.
- The general GKE node pool has `0` nodes and no GKE worker VM instances.
- API/frontend PodDisruptionBudgets are removed because there are no
  multi-replica rollouts to protect.
- The frontend `LoadBalancer` service, GKE cluster, Cloud SQL, Redis, GCS asset
  bucket, Artifact Registry repositories, and Terraform state bucket remain.
  These are expected retained platform resources for this mode and may still
  incur cost.

Destroy only when portfolio QA is complete and evidence is recorded:

```powershell
terraform -chdir=infra/gcp destroy `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "ai_provider=mock"
```
