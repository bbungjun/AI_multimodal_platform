# GCP Terraform

This directory contains the Terraform stack for deploying CreativeOps Studio to
Google Cloud. The first deployment path is GKE-first and starts in
`AI_PROVIDER=mock`; Vertex mode is enabled only after the no-cost mock checks
pass.

## Static Validation

Run local static checks without remote state:

```powershell
terraform -chdir=infra/gcp init -backend=false
terraform -chdir=infra/gcp fmt -recursive -check
terraform -chdir=infra/gcp validate
```

Or use the repository helper:

```powershell
.\scripts\verify_gcp_terraform.ps1
```

## Remote State

The committed backend block uses a placeholder bucket so static validation can
run without a real project id. For a live deployment, create a GCS state bucket
first. Then copy the example backend config to the ignored local file:

```powershell
Copy-Item infra/gcp/backend.hcl.example infra/gcp/backend.hcl
```

Edit `infra/gcp/backend.hcl` locally with the real bucket name before running:

```powershell
terraform -chdir=infra/gcp init -backend-config=backend.hcl
```

`backend.hcl`, `.tfvars`, Terraform state, credentials, and runtime secrets must
stay local and uncommitted.

## Personal GCP Guard

This repository must deploy only to the personal CreativeOps GCP project. Start
every GCP deployment shell with:

```powershell
.\scripts\use_personal_gcp.ps1
gcloud config get-value account
gcloud config get-value project
```

The expected account is `youngjun3108@gmail.com` and the expected project is
`krafton-vertex-live-3108`. The helper sets `CLOUDSDK_CONFIG`, `KUBECONFIG`,
`GOOGLE_CLOUD_PROJECT`, `CLOUDSDK_CORE_PROJECT`, `TF_VAR_gcp_project_id`, and
clears local credential-file environment variables. Guarded deployment helpers
refuse to run against the known team account/project.

## Secret Safety

Do not put DB passwords, `DATABASE_URL`, ADC files, service-account JSON, API
keys, or private keys into Terraform variables, committed files, PR comments, or
terminal output. Runtime secrets are bootstrapped after infrastructure exists.

## Managed Services

The first managed services layer creates private Cloud SQL PostgreSQL,
Memorystore Redis over private service access, a public-access-blocked Cloud
Storage asset bucket, and a Secret Manager container for `DATABASE_URL`. Secret
versions and database passwords are intentionally created later by an explicit
bootstrap script, not by committed Terraform values.

## GKE Identity Boundary

GKE uses a custom node Google service account for image pulls, logging, and
metrics. Application pods use the Kubernetes service account name
`creativeops-app`, which maps to the app Google service account through Workload
Identity. No service-account key files are created or mounted.

## GKE Rollout Boundary

The API and frontend are user-facing workloads and use readiness-gated rolling
updates with `maxUnavailable=0` and `maxSurge=1`. Validate rollout safety with
at least two API and frontend replicas. Terraform requires `node_count >= 2`
when `api_replicas > 1` or `frontend_replicas > 1`; this prevents a
multi-replica rollout plan from running on a single-node pool where replacement
pods can remain Pending with `Insufficient cpu` while old pods are intentionally
kept serving. Worker and dispatcher rollout evidence is different: the worker
is judged by task redelivery/repair safety, and the dispatcher remains
singleton unless a future issue proves multi-dispatcher outbox locking.

## Deployment Helpers

- `scripts/build_push_gcp_images.ps1` builds backend/frontend images and pushes
  them to the Terraform-created Artifact Registry repositories.
- `scripts/bootstrap_gcp_runtime_secrets.ps1` creates or rotates the Cloud SQL
  app user password, adds a Secret Manager version for `DATABASE_URL`, and
  applies the Kubernetes runtime Secret without printing secret values.
- `docs/runbooks/gcp-gke.md` is the operator runbook for mock-first deployment,
  Vertex readiness, and scale-down/teardown.

## Cost-Control Boundary

For a temporary demo pause, set all workload replicas to `0`, set
`node_count=0`, and switch `ai_provider=mock`. This removes app pods and GKE
worker VMs while keeping the GKE control plane, frontend LoadBalancer service,
Cloud SQL, Redis, GCS assets bucket, Artifact Registry repositories, and
Terraform state bucket available for a later resume. Use Terraform `destroy`
only when full teardown is intended and the retained data/state implications
are understood.

## Autoscaling Boundary

GKE node pool autoscaling is available through explicit Terraform variables but
is disabled by default. Keep the fixed `node_count=2` rollout baseline for live
resume and zero-downtime evidence until a separate autoscaling validation issue
records min/max node counts, k6 readiness results, Pending pod behavior, and a
rollback path. Do not enable autoscaling as a hidden side effect of routine
deploy, pause, or resume commands.

## Workload HPA Boundary

API and frontend HorizontalPodAutoscalers are available through explicit
Terraform variables but are disabled by default. Enable them only for a
dedicated HPA validation issue. When HPA is enabled, keep `api_replicas` equal
to `api_hpa_min_replicas` and `frontend_replicas` equal to
`frontend_hpa_min_replicas`; Terraform declares the initial floor, while the
HPA controller owns runtime scale decisions during load. Record k6 readiness or
stress evidence, HPA min/max/target values, node count behavior, and the
rollback apply back to `api_hpa_enabled=false` and
`frontend_hpa_enabled=false`.

## Managed Prometheus Boundary

The API exposes process-local counters and latency summaries at `/metrics`.
GKE Managed Service for Prometheus is explicitly enabled, and the
namespace-scoped `PodMonitoring` resource scrapes each API pod every 30
seconds. Route labels come from FastAPI route templates, not raw URLs, and the
exporter never includes request bodies, prompt text, environment values, or
Secret payloads.

Cloud Monitoring alert policies are disabled by default through
`monitoring_alerts_enabled=false`. Verify metric ingestion and PromQL queries
before enabling policies. Existing notification channel resource names can be
passed through `monitoring_notification_channel_names`; Terraform does not
create or embed email, webhook, or credential values in this stack.
