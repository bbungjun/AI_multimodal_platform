# GCP GKE Terraform Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GCP-first Terraform deployment path that runs CreativeOps Studio on GKE and highlights Kubernetes-based AI platform operations.

**Architecture:** Add a new `infra/gcp/` stack instead of rewriting `infra/aws/`. GKE runs the frontend, API, Celery worker, and outbox dispatcher; Cloud SQL PostgreSQL, Memorystore Redis, Artifact Registry, Secret Manager, and a Cloud Storage FUSE asset bucket provide managed platform services. The first deploy path uses `AI_PROVIDER=mock`; Vertex mode uses GKE Workload Identity and ADC without committing credential JSON.

**Tech Stack:** Terraform 1.10+, HashiCorp Google provider 7.x, Kubernetes provider, Google Cloud SDK, GKE Standard, Artifact Registry, Cloud SQL PostgreSQL, Memorystore Redis, Cloud Storage FUSE CSI driver, FastAPI, Celery, React/Vite, nginx.

---

## Operating Context

- GitHub issue: `#3 Add GCP GKE Terraform deployment path`
- Branch: `codex/issue-3-gcp-gke-terraform`
- Base branch: `main`
- Current AWS deployment: no live AWS stack is running.
- Current runtime shape: `backend`, `worker`, and `dispatcher` share one backend image; frontend uses Vite and currently has only a dev-server Dockerfile.
- Provider boundary: `AI_PROVIDER=mock` must not construct Vertex clients; `AI_PROVIDER=vertex` can use ADC when `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_APPLICATION_CREDENTIALS_JSON` are unset.

## Architecture Decisions

- Keep `infra/aws/` intact for historical AWS redeploys. Put all GCP work under `infra/gcp/`.
- Use GKE Standard with one small managed node pool for the first portfolio deployment. This exposes Kubernetes primitives clearly: namespace, service accounts, deployments, services, probes, requests, limits, PVC, and Workload Identity.
- Run frontend inside GKE through a production nginx image. nginx serves the Vite build and proxies `/api` and `/files` to the backend ClusterIP service, keeping browser requests same-origin and avoiding first-pass Cloud CDN/domain complexity.
- Keep generated media code unchanged by mounting a Cloud Storage bucket at `/data/assets` through the Cloud Storage FUSE CSI driver.
- Use Cloud SQL private IP and Memorystore private service access. Do not expose database or Redis publicly.
- Do not put DB passwords, `DATABASE_URL`, service-account JSON, `.env`, or Terraform tfvars into Git. Runtime DB secrets are bootstrapped by a local script into Kubernetes Secret and GCP Secret Manager without printing values.
- Start with `AI_PROVIDER=mock` and desired replicas `api=1`, `frontend=1`, `worker=1`, `dispatcher=1`. Switch to `vertex` only after mock smoke checks pass.
- Keep GPU node pools out of the first apply. Document the extension point with labels and variables so the portfolio can explain how GPU workloads would be isolated.

## File Structure

- Modify: `AGENTS.md`
  - Persist the Issue -> branch -> PR workflow requested for this repository.
- Modify: `docs/current-work.md`
  - Record Issue #3, the active branch, and this plan as the current handoff.
- Create: `docs/runbooks/gcp-gke-terraform.md`
  - Human deployment runbook for Terraform init/apply, image push, secret bootstrap, smoke checks, Vertex switch, and teardown.
- Create: `infra/gcp/README.md`
  - Stack overview and quick commands.
- Create: `infra/gcp/backend.hcl.example`
  - GCS backend config template.
- Create: `infra/gcp/versions.tf`
  - Terraform and provider versions.
- Create: `infra/gcp/variables.tf`
  - GCP region, cluster, image, replica, provider-mode, and runtime settings.
- Create: `infra/gcp/locals.tf`
  - Shared names, labels, image names, and environment values.
- Create: `infra/gcp/apis.tf`
  - Required Google APIs.
- Create: `infra/gcp/networking.tf`
  - VPC, subnet, private service access, and firewall baseline.
- Create: `infra/gcp/artifact-registry.tf`
  - Docker repositories for backend and frontend images.
- Create: `infra/gcp/cloud-sql.tf`
  - Private Cloud SQL PostgreSQL instance and database.
- Create: `infra/gcp/redis.tf`
  - Memorystore Redis broker.
- Create: `infra/gcp/storage.tf`
  - Cloud Storage bucket for `/data/assets`.
- Create: `infra/gcp/iam.tf`
  - GKE node service account, app Google service account, Workload Identity binding, and IAM roles.
- Create: `infra/gcp/gke.tf`
  - GKE cluster, node pool, Workload Identity, and GCS Fuse CSI addon.
- Create: `infra/gcp/kubernetes-provider.tf`
  - Kubernetes provider wiring from GKE outputs.
- Create: `infra/gcp/k8s-namespace.tf`
  - Namespace and Kubernetes service account.
- Create: `infra/gcp/k8s-config.tf`
  - Runtime ConfigMap, GCS Fuse PV, and PVC.
- Create: `infra/gcp/k8s-workloads.tf`
  - Deployments and Services for frontend, API, worker, and dispatcher.
- Create: `infra/gcp/outputs.tf`
  - Image repository URLs, cluster connection command, service IP, private endpoints, and secret names.
- Create: `frontend/Dockerfile.prod`
  - Production frontend image for GKE.
- Create: `frontend/nginx.conf`
  - SPA static serving and API proxy config.
- Create: `scripts/build_push_gcp_images.ps1`
  - Build and push backend/frontend images to Artifact Registry.
- Create: `scripts/bootstrap_gcp_runtime_secrets.ps1`
  - Create or rotate Cloud SQL app user password, store `DATABASE_URL`, and create Kubernetes runtime secret.
- Create: `scripts/verify_gcp_terraform.ps1`
  - Format and validate `infra/gcp` without applying resources.

## Task 1: Persist GitHub Workflow And Handoff

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/current-work.md`

- [ ] **Step 1: Add the repository workflow rule to `AGENTS.md`**

Add these bullets under `## 저장소와 Git` after the remote repository bullet:

````markdown
- 구현 작업은 먼저 GitHub Issue를 발행해 범위와 수용 기준을 기록합니다.
- 작업 브랜치는 해당 Issue에서 만들고 `codex/issue-번호-짧은-설명` 형식을
  사용합니다.
- 검증이 끝나면 브랜치를 push하고 `main` 대상으로 draft PR을 엽니다.
````

- [ ] **Step 2: Record the current GCP plan in `docs/current-work.md`**

Add this bullet near the top of `## Next Suggested Work`:

````markdown
- Issue #3 is tracking the GCP GKE Terraform deployment path on branch
  `codex/issue-3-gcp-gke-terraform`. The implementation plan lives at
  `docs/superpowers/plans/2026-07-08-gcp-gke-terraform.md` and should be
  executed before creating `infra/gcp/` resources.
````

- [ ] **Step 3: Commit the workflow docs**

Run:

```powershell
git add AGENTS.md docs/current-work.md docs/superpowers/plans/2026-07-08-gcp-gke-terraform.md
git commit -m "docs: plan gcp gke terraform deployment"
```

Expected:

```text
Commit succeeds on branch codex/issue-3-gcp-gke-terraform.
```

## Task 2: Add GCP Terraform Foundation

**Files:**
- Create: `infra/gcp/README.md`
- Create: `infra/gcp/backend.hcl.example`
- Create: `infra/gcp/versions.tf`
- Create: `infra/gcp/variables.tf`
- Create: `infra/gcp/locals.tf`
- Create: `infra/gcp/apis.tf`
- Create: `scripts/verify_gcp_terraform.ps1`

- [ ] **Step 1: Create `infra/gcp/versions.tf`**

```hcl
terraform {
  required_version = ">= 1.10.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
  }

  backend "gcs" {}
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region

  default_labels = local.labels
}
```

- [ ] **Step 2: Create `infra/gcp/variables.tf`**

```hcl
variable "project_name" {
  type    = string
  default = "creativeops"
}

variable "environment" {
  type    = string
  default = "portfolio"
}

variable "gcp_project_id" {
  type        = string
  description = "Google Cloud project id where the portfolio stack is deployed."
}

variable "gcp_region" {
  type    = string
  default = "asia-northeast3"
}

variable "gcp_zone" {
  type    = string
  default = "asia-northeast3-a"
}

variable "network_cidr" {
  type    = string
  default = "10.50.0.0/20"
}

variable "pods_cidr" {
  type    = string
  default = "10.52.0.0/16"
}

variable "services_cidr" {
  type    = string
  default = "10.53.0.0/20"
}

variable "node_machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "node_count" {
  type    = number
  default = 1
}

variable "backend_image" {
  type        = string
  description = "Full Artifact Registry backend image URI including tag."
}

variable "frontend_image" {
  type        = string
  description = "Full Artifact Registry frontend image URI including tag."
}

variable "api_replicas" {
  type    = number
  default = 1
}

variable "frontend_replicas" {
  type    = number
  default = 1
}

variable "worker_replicas" {
  type    = number
  default = 1
}

variable "dispatcher_replicas" {
  type    = number
  default = 1
}

variable "ai_provider" {
  type    = string
  default = "mock"

  validation {
    condition     = contains(["mock", "vertex"], var.ai_provider)
    error_message = "ai_provider must be mock or vertex."
  }
}

variable "vertex_location" {
  type    = string
  default = "us-central1"
}

variable "enhance_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "db_name" {
  type    = string
  default = "multimodal"
}

variable "db_username" {
  type    = string
  default = "app"
}

variable "db_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "redis_memory_size_gb" {
  type    = number
  default = 1
}

variable "rate_limit_gemini_per_min" {
  type    = number
  default = 10
}

variable "rate_limit_imagen_per_min" {
  type    = number
  default = 5
}

variable "rate_limit_veo_per_min" {
  type    = number
  default = 1
}

variable "celery_worker_concurrency" {
  type    = number
  default = 2
}
```

- [ ] **Step 3: Create `infra/gcp/locals.tf`**

```hcl
locals {
  name_prefix = "${var.project_name}-${var.environment}"
  namespace   = local.name_prefix

  labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }

  backend_repository_id  = "${local.name_prefix}-backend"
  frontend_repository_id = "${local.name_prefix}-frontend"
  assets_bucket_name     = "${local.name_prefix}-assets-${var.gcp_project_id}"

  backend_common_environment = {
    AI_PROVIDER                         = var.ai_provider
    DATA_DIR                            = "/data/assets"
    JOB_RUNNER_AUTO_START               = "false"
    JOB_DISPATCH_MODE                   = "celery"
    CELERY_BROKER_URL                   = "redis://${google_redis_instance.main.host}:6379/0"
    CELERY_DEFAULT_QUEUE                = "generation"
    RATE_LIMIT_GEMINI_PER_MIN           = tostring(var.rate_limit_gemini_per_min)
    RATE_LIMIT_IMAGEN_PER_MIN           = tostring(var.rate_limit_imagen_per_min)
    RATE_LIMIT_VEO_PER_MIN              = tostring(var.rate_limit_veo_per_min)
    PROVIDER_RETRY_MAX_ATTEMPTS         = "3"
    PROVIDER_RETRY_BASE_DELAY_SEC       = "1.0"
    PROVIDER_RETRY_MAX_DELAY_SEC        = "20.0"
    CELERY_TASK_ACKS_LATE               = "true"
    CELERY_TASK_REJECT_ON_WORKER_LOST   = "true"
    CELERY_WORKER_PREFETCH_MULTIPLIER   = "1"
    GCP_PROJECT_ID                      = var.gcp_project_id
    GCP_LOCATION                        = var.vertex_location
    ENHANCE_MODEL                       = var.enhance_model
    CORS_ORIGINS                        = "[]"
  }
}
```

- [ ] **Step 4: Create `infra/gcp/apis.tf`**

```hcl
locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com"
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.gcp_project_id
  service            = each.value
  disable_on_destroy = false
}
```

- [ ] **Step 5: Create `infra/gcp/backend.hcl.example`**

```hcl
bucket = "creativeops-terraform-state-PROJECT_ID"
prefix = "creativeops/portfolio/gcp"
```

- [ ] **Step 6: Create `infra/gcp/README.md`**

````markdown
# GCP Terraform 구현 메모

이 디렉터리는 CreativeOps Studio의 GCP/GKE 포트폴리오 배포용 Terraform
stack입니다. 첫 목표는 `AI_PROVIDER=mock`으로 GKE에서 frontend, API,
worker, dispatcher가 Cloud SQL, Memorystore, Cloud Storage FUSE asset
bucket과 연결되는지 검증하는 것입니다.

## 기본 순서

```powershell
cd infra/gcp
terraform init -backend=false
terraform fmt -recursive -check
terraform validate
```

실제 remote state를 사용할 때는 GCS state bucket을 먼저 만든 뒤
`backend.hcl.example`을 복사해서 값을 채웁니다.

```powershell
Copy-Item backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
```

## Secret 원칙

DB password, `DATABASE_URL`, Vertex service-account JSON은 Terraform 변수,
committed 파일, 터미널 출력에 남기지 않습니다. 런타임 secret은
`scripts/bootstrap_gcp_runtime_secrets.ps1`로 Cloud SQL user, Secret Manager,
Kubernetes Secret에 주입합니다.
````

- [ ] **Step 7: Create `scripts/verify_gcp_terraform.ps1`**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location (Join-Path $repoRoot "infra/gcp")

terraform init -backend=false
terraform fmt -recursive -check
terraform validate
```

- [ ] **Step 8: Verify the foundation files**

Run:

```powershell
.\scripts\verify_gcp_terraform.ps1
```

Expected:

```text
Terraform initializes locally with -backend=false, formatting check passes, and validate passes after all referenced resources from later tasks exist.
```

- [ ] **Step 9: Commit the Terraform foundation**

Run:

```powershell
git add infra/gcp/README.md infra/gcp/backend.hcl.example infra/gcp/versions.tf infra/gcp/variables.tf infra/gcp/locals.tf infra/gcp/apis.tf scripts/verify_gcp_terraform.ps1
git commit -m "feat: add gcp terraform foundation"
```

## Task 3: Add Managed GCP Data And Storage Services

**Files:**
- Create: `infra/gcp/networking.tf`
- Create: `infra/gcp/cloud-sql.tf`
- Create: `infra/gcp/redis.tf`
- Create: `infra/gcp/storage.tf`

- [ ] **Step 1: Create `infra/gcp/networking.tf`**

```hcl
resource "google_compute_network" "main" {
  name                    = "${local.name_prefix}-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "gke" {
  name          = "${local.name_prefix}-gke"
  ip_cidr_range = var.network_cidr
  network       = google_compute_network.main.id
  region        = var.gcp_region

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}

resource "google_compute_global_address" "private_service_range" {
  name          = "${local.name_prefix}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]

  depends_on = [google_project_service.required]
}
```

- [ ] **Step 2: Create `infra/gcp/cloud-sql.tf`**

```hcl
resource "google_sql_database_instance" "main" {
  name             = local.name_prefix
  database_version = "POSTGRES_16"
  region           = var.gcp_region

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 20
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
  }

  deletion_protection = var.db_deletion_protection

  depends_on = [google_service_networking_connection.private_services]
}

resource "google_sql_database" "app" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${local.name_prefix}-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}
```

- [ ] **Step 3: Create `infra/gcp/redis.tf`**

```hcl
resource "google_redis_instance" "main" {
  name           = "${local.name_prefix}-redis"
  tier           = "BASIC"
  memory_size_gb = var.redis_memory_size_gb
  region         = var.gcp_region

  authorized_network = google_compute_network.main.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"

  depends_on = [google_service_networking_connection.private_services]
}
```

- [ ] **Step 4: Create `infra/gcp/storage.tf`**

```hcl
resource "google_storage_bucket" "assets" {
  name                        = local.assets_bucket_name
  location                    = var.gcp_region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}
```

- [ ] **Step 5: Run targeted Terraform formatting**

Run:

```powershell
terraform fmt -recursive infra/gcp
```

Expected:

```text
Terraform rewrites files only for formatting or prints no output if already formatted.
```

- [ ] **Step 6: Commit data and storage services**

Run:

```powershell
git add infra/gcp/networking.tf infra/gcp/cloud-sql.tf infra/gcp/redis.tf infra/gcp/storage.tf
git commit -m "feat: add gcp data services"
```

## Task 4: Add Artifact Registry, IAM, And GKE

**Files:**
- Create: `infra/gcp/artifact-registry.tf`
- Create: `infra/gcp/iam.tf`
- Create: `infra/gcp/gke.tf`

- [ ] **Step 1: Create `infra/gcp/artifact-registry.tf`**

```hcl
resource "google_artifact_registry_repository" "backend" {
  location      = var.gcp_region
  repository_id = local.backend_repository_id
  description   = "CreativeOps backend images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_artifact_registry_repository" "frontend" {
  location      = var.gcp_region
  repository_id = local.frontend_repository_id
  description   = "CreativeOps frontend images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}
```

- [ ] **Step 2: Create `infra/gcp/iam.tf`**

```hcl
resource "google_service_account" "gke_node" {
  account_id   = "${local.name_prefix}-gke-node"
  display_name = "CreativeOps GKE node service account"
}

resource "google_service_account" "app" {
  account_id   = "${local.name_prefix}-app"
  display_name = "CreativeOps app workload identity"
}

resource "google_project_iam_member" "node_artifact_reader" {
  project = var.gcp_project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_node.email}"
}

resource "google_project_iam_member" "node_log_writer" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_node.email}"
}

resource "google_project_iam_member" "node_metric_writer" {
  project = var.gcp_project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_node.email}"
}

resource "google_project_iam_member" "app_vertex_user" {
  project = var.gcp_project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_storage_bucket_iam_member" "app_assets_object_admin" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app.email}"
}

resource "google_service_account_iam_member" "app_workload_identity" {
  service_account_id = google_service_account.app.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.gcp_project_id}.svc.id.goog[${local.namespace}/creativeops-app]"
}
```

- [ ] **Step 3: Create `infra/gcp/gke.tf`**

```hcl
resource "google_container_cluster" "main" {
  name     = local.name_prefix
  location = var.gcp_zone

  network    = google_compute_network.main.id
  subnetwork = google_compute_subnetwork.gke.id

  remove_default_node_pool = true
  initial_node_count       = 1

  deletion_protection = false

  workload_identity_config {
    workload_pool = "${var.gcp_project_id}.svc.id.goog"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  addons_config {
    gcs_fuse_csi_driver_config {
      enabled = true
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_container_node_pool" "general" {
  name     = "${local.name_prefix}-general"
  cluster  = google_container_cluster.main.name
  location = google_container_cluster.main.location

  node_count = var.node_count

  node_config {
    machine_type    = var.node_machine_type
    service_account = google_service_account.gke_node.email

    labels = {
      workload = "creativeops-general"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}
```

- [ ] **Step 4: Commit platform IAM and GKE**

Run:

```powershell
git add infra/gcp/artifact-registry.tf infra/gcp/iam.tf infra/gcp/gke.tf
git commit -m "feat: add gke platform resources"
```

## Task 5: Add Production Frontend Container

**Files:**
- Create: `frontend/Dockerfile.prod`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: Create `frontend/nginx.conf`**

```nginx
server {
    listen 8080;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://creativeops-api:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /files/ {
        proxy_pass http://creativeops-api:8000/files/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 2: Create `frontend/Dockerfile.prod`**

```dockerfile
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ENV VITE_API_BASE=
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
```

- [ ] **Step 3: Verify frontend production image builds**

Run:

```powershell
docker build -f frontend/Dockerfile.prod -t creativeops-frontend:gke ./frontend
```

Expected:

```text
Docker build exits with code 0 and produces image creativeops-frontend:gke.
```

- [ ] **Step 4: Commit frontend production container**

Run:

```powershell
git add frontend/Dockerfile.prod frontend/nginx.conf
git commit -m "feat: add gke frontend image"
```

## Task 6: Add Kubernetes Terraform Workloads

**Files:**
- Create: `infra/gcp/kubernetes-provider.tf`
- Create: `infra/gcp/k8s-namespace.tf`
- Create: `infra/gcp/k8s-config.tf`
- Create: `infra/gcp/k8s-workloads.tf`
- Create: `infra/gcp/outputs.tf`

- [ ] **Step 1: Create `infra/gcp/kubernetes-provider.tf`**

```hcl
data "google_client_config" "current" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.main.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.main.master_auth[0].cluster_ca_certificate)
}
```

- [ ] **Step 2: Create `infra/gcp/k8s-namespace.tf`**

```hcl
resource "kubernetes_namespace_v1" "app" {
  metadata {
    name = local.namespace
    labels = {
      app = "creativeops"
    }
  }

  depends_on = [google_container_node_pool.general]
}

resource "kubernetes_service_account_v1" "app" {
  metadata {
    name      = "creativeops-app"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.app.email
    }
  }
}
```

- [ ] **Step 3: Create `infra/gcp/k8s-config.tf`**

```hcl
resource "kubernetes_config_map_v1" "backend_env" {
  metadata {
    name      = "creativeops-backend-env"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  data = local.backend_common_environment
}

resource "kubernetes_persistent_volume_v1" "assets" {
  metadata {
    name = "${local.name_prefix}-assets"
  }

  spec {
    capacity = {
      storage = "1Ti"
    }
    access_modes                     = ["ReadWriteMany"]
    persistent_volume_reclaim_policy = "Retain"
    storage_class_name               = ""

    persistent_volume_source {
      csi {
        driver        = "gcsfuse.csi.storage.gke.io"
        volume_handle = google_storage_bucket.assets.name
      }
    }
  }
}

resource "kubernetes_persistent_volume_claim_v1" "assets" {
  metadata {
    name      = "creativeops-assets"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    access_modes       = ["ReadWriteMany"]
    storage_class_name = ""
    volume_name        = kubernetes_persistent_volume_v1.assets.metadata[0].name

    resources {
      requests = {
        storage = "1Ti"
      }
    }
  }
}
```

- [ ] **Step 4: Create `infra/gcp/k8s-workloads.tf`**

```hcl
locals {
  app_secret_name = "creativeops-runtime-secrets"

  asset_volume = {
    name = "assets"
  }
}

resource "kubernetes_deployment_v1" "api" {
  metadata {
    name      = "creativeops-api"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-api"
    }
  }

  spec {
    replicas = var.api_replicas

    selector {
      match_labels = {
        app = "creativeops-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-api"
        }
        annotations = {
          "gke-gcsfuse/volumes" = "true"
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.app.metadata[0].name

        volume {
          name = "assets"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.assets.metadata[0].name
          }
        }

        container {
          name    = "api"
          image   = var.backend_image
          command = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

          port {
            container_port = 8000
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.backend_env.metadata[0].name
            }
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = local.app_secret_name
                key  = "DATABASE_URL"
              }
            }
          }

          volume_mount {
            name       = "assets"
            mount_path = "/data/assets"
          }

          readiness_probe {
            http_get {
              path = "/api/health"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          resources {
            requests = {
              cpu    = "250m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "api" {
  metadata {
    name      = "creativeops-api"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    selector = {
      app = "creativeops-api"
    }

    port {
      port        = 8000
      target_port = 8000
    }
  }
}

resource "kubernetes_deployment_v1" "worker" {
  metadata {
    name      = "creativeops-worker"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-worker"
    }
  }

  spec {
    replicas = var.worker_replicas

    selector {
      match_labels = {
        app = "creativeops-worker"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-worker"
        }
        annotations = {
          "gke-gcsfuse/volumes" = "true"
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.app.metadata[0].name

        volume {
          name = "assets"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.assets.metadata[0].name
          }
        }

        container {
          name    = "worker"
          image   = var.backend_image
          command = ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--queues=generation", "--concurrency=${var.celery_worker_concurrency}"]

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.backend_env.metadata[0].name
            }
          }

          env {
            name  = "CELERY_WORKER_CONCURRENCY"
            value = tostring(var.celery_worker_concurrency)
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = local.app_secret_name
                key  = "DATABASE_URL"
              }
            }
          }

          volume_mount {
            name       = "assets"
            mount_path = "/data/assets"
          }

          resources {
            requests = {
              cpu    = "500m"
              memory = "1Gi"
            }
            limits = {
              cpu    = "1"
              memory = "2Gi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_deployment_v1" "dispatcher" {
  metadata {
    name      = "creativeops-dispatcher"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-dispatcher"
    }
  }

  spec {
    replicas = var.dispatcher_replicas

    selector {
      match_labels = {
        app = "creativeops-dispatcher"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-dispatcher"
        }
      }

      spec {
        service_account_name = kubernetes_service_account_v1.app.metadata[0].name

        container {
          name    = "dispatcher"
          image   = var.backend_image
          command = ["python", "-m", "app.services.jobs.outbox_dispatcher"]

          env_from {
            config_map_ref {
              name = kubernetes_config_map_v1.backend_env.metadata[0].name
            }
          }

          env {
            name = "DATABASE_URL"
            value_from {
              secret_key_ref {
                name = local.app_secret_name
                key  = "DATABASE_URL"
              }
            }
          }

          env {
            name  = "OUTBOX_DISPATCHER_BATCH_SIZE"
            value = "50"
          }

          env {
            name  = "OUTBOX_DISPATCHER_POLL_INTERVAL_SEC"
            value = "1.0"
          }

          env {
            name  = "OUTBOX_DISPATCHER_MAX_ATTEMPTS"
            value = "10"
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_deployment_v1" "frontend" {
  metadata {
    name      = "creativeops-frontend"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
    labels = {
      app = "creativeops-frontend"
    }
  }

  spec {
    replicas = var.frontend_replicas

    selector {
      match_labels = {
        app = "creativeops-frontend"
      }
    }

    template {
      metadata {
        labels = {
          app = "creativeops-frontend"
        }
      }

      spec {
        container {
          name  = "frontend"
          image = var.frontend_image

          port {
            container_port = 8080
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 8080
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "256Mi"
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "frontend" {
  metadata {
    name      = "creativeops-frontend"
    namespace = kubernetes_namespace_v1.app.metadata[0].name
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "creativeops-frontend"
    }

    port {
      port        = 80
      target_port = 8080
    }
  }
}
```

- [ ] **Step 5: Create `infra/gcp/outputs.tf`**

```hcl
output "backend_repository_url" {
  value = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.backend.repository_id}"
}

output "frontend_repository_url" {
  value = "${var.gcp_region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.frontend.repository_id}"
}

output "cluster_get_credentials_command" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.main.name} --zone ${var.gcp_zone} --project ${var.gcp_project_id}"
}

output "namespace" {
  value = kubernetes_namespace_v1.app.metadata[0].name
}

output "frontend_service_name" {
  value = kubernetes_service_v1.frontend.metadata[0].name
}

output "cloud_sql_instance_name" {
  value = google_sql_database_instance.main.name
}

output "cloud_sql_private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}

output "database_name" {
  value = google_sql_database.app.name
}

output "database_url_secret_name" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "redis_host" {
  value = google_redis_instance.main.host
}

output "assets_bucket_name" {
  value = google_storage_bucket.assets.name
}
```

- [ ] **Step 6: Commit Kubernetes resources**

Run:

```powershell
git add infra/gcp/kubernetes-provider.tf infra/gcp/k8s-namespace.tf infra/gcp/k8s-config.tf infra/gcp/k8s-workloads.tf infra/gcp/outputs.tf
git commit -m "feat: add gke workload resources"
```

## Task 7: Add GCP Build And Secret Bootstrap Scripts

**Files:**
- Create: `scripts/build_push_gcp_images.ps1`
- Create: `scripts/bootstrap_gcp_runtime_secrets.ps1`

- [ ] **Step 1: Create `scripts/build_push_gcp_images.ps1`**

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectId,

    [string] $Region = "asia-northeast3",
    [string] $Tag = "portfolio"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
Set-Location $repoRoot

$backendRepository = "$Region-docker.pkg.dev/$ProjectId/creativeops-portfolio-backend/creativeops-backend"
$frontendRepository = "$Region-docker.pkg.dev/$ProjectId/creativeops-portfolio-frontend/creativeops-frontend"

gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet

docker build -t "${backendRepository}:${Tag}" ./backend
docker push "${backendRepository}:${Tag}"

docker build -f frontend/Dockerfile.prod -t "${frontendRepository}:${Tag}" ./frontend
docker push "${frontendRepository}:${Tag}"

Write-Host "Backend image: ${backendRepository}:${Tag}"
Write-Host "Frontend image: ${frontendRepository}:${Tag}"
```

- [ ] **Step 2: Create `scripts/bootstrap_gcp_runtime_secrets.ps1`**

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectId,

    [string] $Region = "asia-northeast3",
    [string] $Zone = "asia-northeast3-a",
    [string] $Environment = "portfolio",
    [string] $DbUser = "app",
    [string] $DbName = "multimodal"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = git rev-parse --show-toplevel
$infraDir = Join-Path $repoRoot "infra/gcp"
Set-Location $infraDir

$namePrefix = "creativeops-$Environment"
$namespace = $namePrefix
$secretName = "creativeops-runtime-secrets"

$cloudSqlInstance = terraform output -raw cloud_sql_instance_name
$cloudSqlPrivateIp = terraform output -raw cloud_sql_private_ip
$databaseUrlSecretName = terraform output -raw database_url_secret_name

$passwordBytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Fill($passwordBytes)
$dbPassword = [Convert]::ToBase64String($passwordBytes)

$existingUsers = gcloud sql users list `
    --project $ProjectId `
    --instance $cloudSqlInstance `
    --format "value(name)"

if ($existingUsers -contains $DbUser) {
    gcloud sql users set-password $DbUser `
        --project $ProjectId `
        --instance $cloudSqlInstance `
        --password $dbPassword
} else {
    gcloud sql users create $DbUser `
        --project $ProjectId `
        --instance $cloudSqlInstance `
        --password $dbPassword
}

$databaseUrl = "postgresql+asyncpg://${DbUser}:$([uri]::EscapeDataString($dbPassword))@${cloudSqlPrivateIp}:5432/${DbName}"

$tmpSecretFile = New-TemporaryFile
try {
    Set-Content -LiteralPath $tmpSecretFile -Value $databaseUrl -NoNewline
    gcloud secrets versions add $databaseUrlSecretName `
        --project $ProjectId `
        --data-file $tmpSecretFile
} finally {
    Remove-Item -LiteralPath $tmpSecretFile -Force
}

gcloud container clusters get-credentials $namePrefix `
    --zone $Zone `
    --project $ProjectId

kubectl create secret generic $secretName `
    --namespace $namespace `
    --from-literal "DATABASE_URL=$databaseUrl" `
    --dry-run=client `
    -o yaml | kubectl apply -f -

Write-Host "Runtime secret refreshed in namespace $namespace."
```

- [ ] **Step 3: Commit scripts**

Run:

```powershell
git add scripts/build_push_gcp_images.ps1 scripts/bootstrap_gcp_runtime_secrets.ps1
git commit -m "feat: add gcp deployment scripts"
```

## Task 8: Add GCP Deployment Runbook

**Files:**
- Create: `docs/runbooks/gcp-gke-terraform.md`
- Modify: `README.md`
- Modify: `docs/provider-modes.md`
- Modify: `docs/storage-and-assets.md`

- [ ] **Step 1: Create `docs/runbooks/gcp-gke-terraform.md`**

````markdown
# GCP GKE Terraform Runbook

Use this runbook for the GCP portfolio deployment tracked by Issue #3.

## Preconditions

- Google Cloud project with billing enabled.
- Local `gcloud` login has permission to manage GKE, Artifact Registry, Cloud
  SQL, Memorystore, Secret Manager, IAM, Compute, and Cloud Storage.
- Terraform 1.10+ is installed.
- Docker is running locally.
- No credential JSON, `.env`, `.tfvars`, or Terraform state file is committed.

## First Mock Deployment

```powershell
gcloud config set project PROJECT_ID
gcloud services enable cloudresourcemanager.googleapis.com
gsutil mb -l asia-northeast3 gs://creativeops-terraform-state-PROJECT_ID
gsutil versioning set on gs://creativeops-terraform-state-PROJECT_ID

cd infra/gcp
Copy-Item backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
terraform fmt -recursive -check
terraform validate
terraform apply `
  -var "gcp_project_id=PROJECT_ID" `
  -var "backend_image=asia-northeast3-docker.pkg.dev/PROJECT_ID/creativeops-portfolio-backend/creativeops-backend:portfolio" `
  -var "frontend_image=asia-northeast3-docker.pkg.dev/PROJECT_ID/creativeops-portfolio-frontend/creativeops-frontend:portfolio"
```

## Build And Push Images

```powershell
.\scripts\build_push_gcp_images.ps1 -ProjectId PROJECT_ID -Region asia-northeast3 -Tag portfolio
```

Run `terraform apply` again with the pushed image URIs if the first apply used
temporary image tags such as `creativeops-backend:portfolio`.

## Bootstrap Runtime Secret

```powershell
.\scripts\bootstrap_gcp_runtime_secrets.ps1 -ProjectId PROJECT_ID -Region asia-northeast3 -Zone asia-northeast3-a
kubectl rollout restart deployment/creativeops-api deployment/creativeops-worker deployment/creativeops-dispatcher -n creativeops-portfolio
```

## Smoke Checks

```powershell
kubectl get pods -n creativeops-portfolio
kubectl get svc creativeops-frontend -n creativeops-portfolio
```

Open the external IP from `creativeops-frontend`.

Expected:

- `/api/health` reports `ok: true`, DB `up`, and `vertex.status=mock_provider`.
- `/api/ops/health` returns job and outbox summaries.
- A mock text-to-image job reaches `completed`.
- Generated media preview loads through `/files/...`.

## Vertex Mode

Switch only after mock checks pass:

```powershell
terraform apply `
  -var "gcp_project_id=PROJECT_ID" `
  -var "ai_provider=vertex" `
  -var "backend_image=asia-northeast3-docker.pkg.dev/PROJECT_ID/creativeops-portfolio-backend/creativeops-backend:portfolio" `
  -var "frontend_image=asia-northeast3-docker.pkg.dev/PROJECT_ID/creativeops-portfolio-frontend/creativeops-frontend:portfolio"
```

The app uses GKE Workload Identity and ADC for Vertex. Do not mount or commit
service-account JSON.

## Teardown

```powershell
terraform destroy `
  -var "gcp_project_id=PROJECT_ID" `
  -var "backend_image=asia-northeast3-docker.pkg.dev/PROJECT_ID/creativeops-portfolio-backend/creativeops-backend:portfolio" `
  -var "frontend_image=asia-northeast3-docker.pkg.dev/PROJECT_ID/creativeops-portfolio-frontend/creativeops-frontend:portfolio"
```
````

- [ ] **Step 2: Add README link**

Add the GCP runbook link near the existing runbook links:

```markdown
- [GCP GKE Terraform runbook](docs/runbooks/gcp-gke-terraform.md)
```

- [ ] **Step 3: Update provider mode docs for GKE Workload Identity**

Add this paragraph to `docs/provider-modes.md` under `## Credentials`:

```markdown
For GKE execution, prefer Workload Identity and ADC. In that mode the pods do
not set `GOOGLE_APPLICATION_CREDENTIALS` or
`GOOGLE_APPLICATION_CREDENTIALS_JSON`; `google-auth` resolves credentials from
the Kubernetes service account mapped to the Google service account.
```

- [ ] **Step 4: Update storage docs for GCS Fuse**

Add this paragraph to `docs/storage-and-assets.md` under `## File Storage`:

```markdown
The GCP GKE deployment keeps the same `DATA_DIR` contract by mounting a Cloud
Storage bucket at `/data/assets` through the Cloud Storage FUSE CSI driver.
The storage helper still owns path containment, reads, writes, deletion, and
streaming; the provider-specific mount stays below the deployment boundary.
```

- [ ] **Step 5: Commit runbook docs**

Run:

```powershell
git add docs/runbooks/gcp-gke-terraform.md README.md docs/provider-modes.md docs/storage-and-assets.md
git commit -m "docs: add gcp gke deployment runbook"
```

## Task 9: Terraform Validation And Local Quality Gate

**Files:**
- No source changes unless validation finds a specific defect.

- [ ] **Step 1: Run GCP Terraform verification**

Run:

```powershell
.\scripts\verify_gcp_terraform.ps1
```

Expected:

```text
terraform init -backend=false succeeds, terraform fmt -recursive -check succeeds, and terraform validate succeeds.
```

- [ ] **Step 2: Run repository hygiene checks**

Run:

```powershell
git diff --check
git status --short --branch
git diff --cached --name-only
```

Expected:

```text
No whitespace errors. Status shows only intentional files before final commit. Staged file list is empty before staging.
```

- [ ] **Step 3: Run full local verification**

Run:

```powershell
python scripts/verify_local.py
```

Expected:

```text
VERIFY PASSED
```

- [ ] **Step 4: Commit verification fixes**

If validation required small fixes, run:

```powershell
git add infra/gcp frontend scripts docs README.md AGENTS.md
git commit -m "fix: stabilize gcp terraform validation"
```

Expected:

```text
Commit is created only when files changed after Task 8.
```

## Task 10: Push Branch And Open Draft PR

**Files:**
- No file edits.

- [ ] **Step 1: Push the issue branch**

Run:

```powershell
git push -u origin codex/issue-3-gcp-gke-terraform
```

Expected:

```text
Remote branch is created on origin.
```

- [ ] **Step 2: Open a draft PR**

Use the GitHub connector or GitHub CLI to open a draft PR:

```powershell
gh pr create `
  --draft `
  --base main `
  --head codex/issue-3-gcp-gke-terraform `
  --title "Add GCP GKE Terraform deployment path" `
  --body-file .github/pr-body-gcp-gke.md
```

PR body content:

```markdown
Closes #3

## Summary

- Adds a GCP/GKE Terraform deployment path under `infra/gcp/`.
- Runs frontend, API, worker, and dispatcher on GKE.
- Uses Cloud SQL PostgreSQL, Memorystore Redis, Artifact Registry, Secret
  Manager, and Cloud Storage FUSE for the portfolio deployment.
- Documents mock-first verification and Workload Identity based Vertex mode.

## Validation

- `.\scripts\verify_gcp_terraform.ps1`
- `python scripts/verify_local.py`
- `git diff --check`

## Notes

- First deployment should use `AI_PROVIDER=mock`.
- Runtime DB secret bootstrap is local and does not commit secret values.
```

Expected:

```text
Draft PR opens against main and links Issue #3.
```

## Review Checklist

- `infra/aws/` remains unchanged unless a documentation cross-reference is needed.
- `AI_PROVIDER=mock` remains the default no-cost deployment path.
- No service-account JSON, `.env`, `.tfvars`, `backend.hcl`, state file, generated media, or DB password is staged.
- Kubernetes workloads use ConfigMap for non-secret runtime values and Kubernetes Secret for `DATABASE_URL`.
- Vertex mode relies on Workload Identity and ADC, not mounted credential JSON.
- The frontend production image proxies `/api` and `/files` to the internal API service.
- `/data/assets` remains the app-facing storage path.
- Terraform validation runs with `-backend=false` for local static checks.
- The final PR is draft unless the user explicitly asks for ready review.

## Official References

- [Terraform Google provider docs](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Using GKE with Terraform](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/using_gke_with_terraform)
- [Terraform Kubernetes provider docs](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs)
- [Google Artifact Registry with Terraform](https://docs.cloud.google.com/artifact-registry/docs/repositories/terraform)
- [Cloud Storage FUSE CSI driver for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cloud-storage-fuse-csi-driver-setup)
- [Access Cloud Storage buckets with the FUSE CSI driver](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/persistent-volumes/cloud-storage-fuse-csi-driver)

## Self-Review

- Spec coverage: Issue workflow, GCP Terraform foundation, data services, GKE, Workload Identity, production frontend image, runtime secret bootstrap, runbook, validation, push, and draft PR are mapped to tasks.
- Placeholder scan: The plan uses concrete paths, commands, resource names, and expected outputs. Secret values are deliberately created by a local bootstrap script and never represented as committed content.
- Type and naming consistency: Terraform locals use `creativeops-portfolio` as the namespace, scripts use the same prefix, and Kubernetes workload names match nginx upstream `creativeops-api`.
- Scope check: GPU node pools, managed certificates, custom domains, Cloud CDN, and object-storage adapter changes are intentionally outside this first deployable GKE path.
