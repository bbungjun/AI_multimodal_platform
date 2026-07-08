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

Scale the app to one replica per workload:

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
python scripts/smoke_mock_golden_path.py --base-url $frontendUrl --timeout-sec 120
```

Expected health mode: `vertex.status=mock_provider`.

## Vertex Readiness

Run this only after mock smoke passes. Imagen and Veo live generation remain out
of scope unless a separate cost-aware QA issue approves them.

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
Invoke-RestMethod -Uri "$frontendUrl/api/health"
```

Expected readiness mode: `vertex.status=ready`.

Run at most one Gemini prompt-enhancement smoke only after confirming the cost
intent in Issue #13.

## Scale Down Or Destroy

Scale app workloads to zero when the demo is not active:

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

Destroy only when portfolio QA is complete and evidence is recorded:

```powershell
terraform -chdir=infra/gcp destroy `
  -var "gcp_project_id=$env:GCP_PROJECT_ID" `
  -var "backend_image=$backendImage" `
  -var "frontend_image=$frontendImage" `
  -var "ai_provider=mock"
```
