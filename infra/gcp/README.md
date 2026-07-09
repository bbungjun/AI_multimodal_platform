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
at least two API and frontend replicas. Worker and dispatcher rollout evidence
is different: the worker is judged by task redelivery/repair safety, and the
dispatcher remains singleton unless a future issue proves multi-dispatcher
outbox locking.

## Deployment Helpers

- `scripts/build_push_gcp_images.ps1` builds backend/frontend images and pushes
  them to the Terraform-created Artifact Registry repositories.
- `scripts/bootstrap_gcp_runtime_secrets.ps1` creates or rotates the Cloud SQL
  app user password, adds a Secret Manager version for `DATABASE_URL`, and
  applies the Kubernetes runtime Secret without printing secret values.
- `docs/runbooks/gcp-gke.md` is the operator runbook for mock-first deployment,
  Vertex readiness, and scale-down/teardown.
