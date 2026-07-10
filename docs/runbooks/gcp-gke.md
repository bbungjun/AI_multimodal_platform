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

## Managed Prometheus And Alert Readiness

The API exposes Prometheus text at `/metrics` on its existing port. The endpoint
contains process-local HTTP counters and duration summaries labeled by method,
FastAPI route template, and status, plus provider failure counters labeled by
controlled error code, provider status, and retryability. It does not contain
request bodies, prompt text, env values, or Secret payloads.

Terraform explicitly enables GKE Managed Service for Prometheus and applies a
namespace-scoped `PodMonitoring` that scrapes every API pod at 30-second
intervals. Keep Cloud Monitoring alert policies disabled during the first
collection rollout:

```powershell
terraform -chdir=infra/gcp plan `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "monitoring_alerts_enabled=false"
```

Confirm the plan does not change provider mode, workload replica counts,
Secrets, Cloud SQL, Redis, or asset storage unexpectedly. After an intentional
apply and API rollout, verify the target and endpoint without printing any
credentials:

```powershell
kubectl get podmonitoring -n creativeops-portfolio
kubectl describe podmonitoring creativeops-api -n creativeops-portfolio
kubectl port-forward deployment/creativeops-api 8000:8000 -n creativeops-portfolio
Invoke-WebRequest -Uri "http://127.0.0.1:8000/metrics"
```

In Cloud Monitoring Metrics Explorer, query
`creativeops_http_requests_total` and
`creativeops_provider_failures_total` with PromQL. Confirm each running API pod
is represented before enabling alerts. The HTTP policy excludes metrics,
health-probe, and unmatched-route traffic, then requires at least 20 application
requests in five minutes and a 5xx ratio above 5%. The provider policy requires
three failures with the same code in five minutes. These defaults avoid a
single low-traffic failure opening an incident.

Attach existing notification channel resource names only through the
`monitoring_notification_channel_names` variable. An empty list still permits
Cloud Monitoring incidents but sends no email, SMS, webhook, or PagerDuty
notification. Do not commit channel credentials or local `.tfvars`.

After ingestion and query checks pass, create the policies with an explicit
plan and apply:

```powershell
terraform -chdir=infra/gcp plan `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "monitoring_alerts_enabled=true" `
  -var 'monitoring_notification_channel_names=[]'
```

Before this or any other GCP write, run the personal GCP guard and verify the
active account and project. Apply only the reviewed plan. The API exports
zero-valued series for the bounded provider error-code set so the provider
policy can be created before the first live failure. If a new alert references
a new label value or metric, first roll out collection, wait until a Prometheus
query returns that series, and only then create the policy. Do not use targeted
Terraform applies as the normal deployment path; they are a recovery tool for
an already-partially-applied rollout and must be followed by a complete plan.

For controlled incident validation, use a dedicated Issue and record the exact
request bound before sending traffic. Establish the counter series first, then
send a second bounded batch inside the policy window because the first sample
of a newly observed cumulative series is its baseline rather than an increase.
Query Managed Prometheus through its Prometheus HTTP API endpoint:

```text
https://monitoring.googleapis.com/v1/projects/PROJECT_ID/location/global/prometheus/api/v1/query
```

Confirm the exact policy PromQL is above threshold before checking the Cloud
Monitoring incident. A model-not-found response is suitable for validating the
safe `vertex_request_invalid` path because it does not generate media and the
public API response does not expose provider payloads. Restore the known-good
provider/model configuration immediately after the incident opens, verify all
rollouts and health endpoints, then wait for both policies to close. Finish
with a complete Terraform plan using the restored variables and require exit
code `0` (`No changes`).

## Dashboard And Availability SLO

Terraform can create a custom monitored service, a request-based availability
SLO, and the `CreativeOps API Reliability` dashboard. These resources are
disabled by default with `monitoring_dashboard_slo_enabled=false`. Keep them
disabled during the first backend rollout because the dashboard p95 chart
depends on the request-duration histogram descriptor being ingested first.

The default objective is **99.5% availability over a rolling 28-day period**.
Eligible traffic excludes `/metrics`, health endpoints, ops metrics/health
endpoints, and unmatched routes. An eligible HTTP 5xx response is bad; all
other eligible responses are good. The corresponding error budget is 0.5% of
eligible requests. A one-hour burn rate above `1` means the current bad-request
rate is consuming that budget faster than the sustainable rate.

First deploy the backend image with the histogram exporter while leaving the
dashboard/SLO disabled. Verify all API pods and the histogram query:

```text
histogram_quantile(0.95,
  sum by (le) (
    rate(creativeops_http_request_duration_milliseconds_bucket{
      namespace="creativeops-portfolio"
    }[5m])
  )
)
```

Then review a complete Terraform plan with the known-good workload, replica,
node-pool, provider, and alert variables plus:

```powershell
terraform -chdir=infra/gcp plan `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "monitoring_alerts_enabled=true" `
  -var "monitoring_dashboard_slo_enabled=true" `
  -var "monitoring_availability_slo_goal=0.995" `
  -var "monitoring_availability_slo_rolling_days=28"
```

The enablement plan should create only the custom service, SLO, and dashboard.
After apply, read the three resources through the Cloud Monitoring API and
query `select_slo_compliance`, `select_slo_budget`, and
`select_slo_burn_rate` for the Terraform SLO name. New SLOs can legitimately
show sparse or no compliance points until eligible request data is available.

This SLI covers application-observed requests only. If all API pods are down,
no process counter can record requests that failed before reaching the app.
Use load-balancer request metrics or a synthetic availability signal before
claiming edge-to-backend availability coverage.

Rollback the dashboard and SLO by reapplying the complete known-good variables
with `monitoring_dashboard_slo_enabled=false`. This deletes only the three
opt-in monitoring resources; it must not disable Managed Prometheus collection,
existing alert policies, or application health probes. Review the destroy plan
before applying it.

Rollback alert evaluation without disabling metric collection by reapplying
with `monitoring_alerts_enabled=false`. If collection itself causes an
unexpected rollout or ingestion issue, first remove the `PodMonitoring` from
Terraform in a dedicated change; do not disable GKE system monitoring or alter
application health probes as an incident shortcut.

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
