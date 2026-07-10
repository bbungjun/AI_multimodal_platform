#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_gcp_release.sh \
  --backend-image IMAGE@sha256:DIGEST \
  --frontend-image IMAGE@sha256:DIGEST \
  [--profile PATH] [--expected-vertex-status STATUS] [--plan-only]

The release profile contains only non-secret live topology and Terraform
settings. The script refuses tag-based images, unexpected Terraform resource
changes, or any GCP account/project other than the personal guard values.
EOF
}

repo_root="$(git rev-parse --show-toplevel)"
profile="$repo_root/infra/gcp/release-profile.json"
terraform_dir="$repo_root/infra/gcp"
backend_image=""
frontend_image=""
expected_vertex_override=""
plan_only=false

while (($#)); do
  case "$1" in
    --backend-image)
      backend_image="${2:-}"
      shift 2
      ;;
    --frontend-image)
      frontend_image="${2:-}"
      shift 2
      ;;
    --profile)
      profile="${2:-}"
      shift 2
      ;;
    --expected-vertex-status)
      expected_vertex_override="${2:-}"
      shift 2
      ;;
    --plan-only)
      plan_only=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$backend_image" || -z "$frontend_image" ]]; then
  usage >&2
  exit 2
fi

gcloud_bin="${GCLOUD_BIN:-gcloud}"
kubectl_bin="${KUBECTL_BIN:-kubectl}"
terraform_bin="${TERRAFORM_BIN:-terraform}"
health_attempts="${RELEASE_HEALTH_ATTEMPTS:-12}"
health_interval_sec="${RELEASE_HEALTH_INTERVAL_SEC:-5}"

if [[ ! "$health_attempts" =~ ^[1-9][0-9]*$ || ! "$health_interval_sec" =~ ^[0-9]+$ ]]; then
  echo "Health retry settings must be positive attempts and a non-negative interval." >&2
  exit 2
fi

for command in git python3 curl base64 "$gcloud_bin" "$kubectl_bin" "$terraform_bin"; do
  if ! command -v "$command" >/dev/null 2>&1 && [[ ! -x "$command" ]]; then
    echo "Required command is unavailable: $command" >&2
    exit 2
  fi
done

profile_keys=(
  api_replicas
  frontend_replicas
  worker_replicas
  dispatcher_replicas
  node_count
  node_pool_autoscaling_enabled
  node_pool_autoscaling_min_count
  node_pool_autoscaling_max_count
  api_hpa_enabled
  frontend_hpa_enabled
  ai_provider
  enhance_model
  monitoring_alerts_enabled
  monitoring_notification_channel_names
  monitoring_dashboard_slo_enabled
  monitoring_availability_slo_goal
  monitoring_availability_slo_rolling_days
)

mapfile -d '' profile_values < <(
  python3 - "$profile" "${profile_keys[@]}" <<'PY'
import json
import sys

path, *terraform_keys = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    profile = json.load(handle)

required = {
    "schema_version",
    "account",
    "project_id",
    "region",
    "cluster_name",
    "cluster_zone",
    "namespace",
    "state_bucket",
    "health_url",
    "expected_vertex_status",
    "terraform_vars",
}
if set(profile) != required or profile["schema_version"] != 1:
    raise SystemExit("Release profile schema does not match version 1")
if set(profile["terraform_vars"]) != set(terraform_keys):
    raise SystemExit("Release profile Terraform variable allowlist mismatch")

top_values = [
    profile["account"],
    profile["project_id"],
    profile["region"],
    profile["cluster_name"],
    profile["cluster_zone"],
    profile["namespace"],
    profile["state_bucket"],
    profile["health_url"],
    profile["expected_vertex_status"],
]

def encode(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        return json.dumps(value, separators=(",", ":"))
    return str(value)

for value in top_values:
    if not isinstance(value, str) or not value:
        raise SystemExit("Release profile contains an empty non-string field")
    print(value, end="\0")
for key in terraform_keys:
    print(encode(profile["terraform_vars"][key]), end="\0")
PY
)

expected_account="${profile_values[0]}"
project_id="${profile_values[1]}"
region="${profile_values[2]}"
cluster_name="${profile_values[3]}"
cluster_zone="${profile_values[4]}"
namespace="${profile_values[5]}"
state_bucket="${profile_values[6]}"
health_url="${profile_values[7]}"
recovery_vertex_status="${profile_values[8]}"
expected_vertex_status="${expected_vertex_override:-$recovery_vertex_status}"

if [[ "$expected_account" != "youngjun3108@gmail.com" || "$project_id" != "krafton-vertex-live-3108" ]]; then
  echo "Release profile does not target the required personal GCP context." >&2
  exit 2
fi

backend_repo="$region-docker.pkg.dev/$project_id/creativeops-portfolio-backend/creativeops-backend"
frontend_repo="$region-docker.pkg.dev/$project_id/creativeops-portfolio-frontend/creativeops-frontend"
valid_digest_image() {
  local image="$1"
  local repository="$2"
  local prefix="$repository@sha256:"
  local digest
  if [[ "$image" != "$prefix"* ]]; then
    return 1
  fi
  digest="${image#"$prefix"}"
  [[ "$digest" =~ ^[a-f0-9]{64}$ ]]
}

if ! valid_digest_image "$backend_image" "$backend_repo"; then
  echo "Backend image must be the personal Artifact Registry repository pinned by digest." >&2
  exit 2
fi
if ! valid_digest_image "$frontend_image" "$frontend_repo"; then
  echo "Frontend image must be the personal Artifact Registry repository pinned by digest." >&2
  exit 2
fi

export CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-$HOME/.gcloud-creativeops-personal}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/creativeops-personal}"
unset GOOGLE_APPLICATION_CREDENTIALS
unset GOOGLE_APPLICATION_CREDENTIALS_HOST
export GOOGLE_CLOUD_PROJECT="$project_id"
export CLOUDSDK_CORE_PROJECT="$project_id"
export TF_VAR_gcp_project_id="$project_id"

active_account="$("$gcloud_bin" config get-value account 2>/dev/null)"
active_project="$("$gcloud_bin" config get-value project 2>/dev/null)"
printf 'account=%s\nproject=%s\n' "$active_account" "$active_project"
if [[ "$active_account" != "$expected_account" || "$active_project" != "$project_id" ]]; then
  echo "Personal GCP guard failed before release operations." >&2
  exit 2
fi

plan_file="$(mktemp /tmp/creativeops-release-plan-XXXXXX)"
rollback_plan_file="$(mktemp /tmp/creativeops-rollback-plan-XXXXXX)"
ca_file=""
access_token=""

cleanup() {
  unset GOOGLE_OAUTH_ACCESS_TOKEN
  access_token=""
  rm -f "$plan_file" "$rollback_plan_file"
  if [[ -n "$ca_file" ]]; then
    rm -f "$ca_file"
  fi
}
trap cleanup EXIT

endpoint="$("$gcloud_bin" container clusters describe "$cluster_name" --zone "$cluster_zone" --format='value(endpoint)')"
ca_base64="$("$gcloud_bin" container clusters describe "$cluster_name" --zone "$cluster_zone" --format='value(masterAuth.clusterCaCertificate)')"
access_token="$("$gcloud_bin" auth print-access-token)"
export GOOGLE_OAUTH_ACCESS_TOKEN="$access_token"

if [[ "$kubectl_bin" == *.exe ]]; then
  ca_file="$(mktemp /mnt/c/Windows/Temp/creativeops-release-ca-XXXXXX.crt)"
else
  ca_file="$(mktemp /tmp/creativeops-release-ca-XXXXXX.crt)"
fi
printf '%s' "$ca_base64" | base64 -d > "$ca_file"
ca_arg="$ca_file"
if [[ "$kubectl_bin" == *.exe ]]; then
  ca_arg="$(wslpath -w "$ca_file")"
fi
kubectl_args=(
  "$kubectl_bin"
  "--server=https://$endpoint"
  "--certificate-authority=$ca_arg"
  "--token=$access_token"
  --namespace "$namespace"
)

running_digest() {
  local label="$1"
  local container="$2"
  "${kubectl_args[@]}" get pods --selector "app=$label" --output json |
    python3 -c '
import json
import sys

container = sys.argv[1]
pods = json.load(sys.stdin).get("items", [])
for pod in pods:
    if pod.get("status", {}).get("phase") != "Running":
        continue
    conditions = pod.get("status", {}).get("conditions", [])
    if not any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions):
        continue
    for status in pod.get("status", {}).get("containerStatuses", []):
        if status.get("name") == container and status.get("ready"):
            image_id = status.get("imageID", "")
            for prefix in ("docker-pullable://", "docker://"):
                if image_id.startswith(prefix):
                    image_id = image_id[len(prefix):]
            print(image_id)
            raise SystemExit(0)
raise SystemExit("No ready running container image digest found")
' "$container"
}

previous_backend="$(running_digest creativeops-api api)"
worker_backend="$(running_digest creativeops-worker worker)"
dispatcher_backend="$(running_digest creativeops-dispatcher dispatcher)"
previous_frontend="$(running_digest creativeops-frontend frontend)"

if [[ "$previous_backend" != "$worker_backend" || "$previous_backend" != "$dispatcher_backend" ]]; then
  echo "Backend deployments are not running the same digest; release aborted." >&2
  exit 2
fi
if ! valid_digest_image "$previous_backend" "$backend_repo" || ! valid_digest_image "$previous_frontend" "$frontend_repo"; then
  echo "Running workloads do not expose expected personal Artifact Registry digests." >&2
  exit 2
fi

terraform_vars=("-var=gcp_project_id=$project_id")
for index in "${!profile_keys[@]}"; do
  value_index=$((9 + index))
  terraform_vars+=("-var=${profile_keys[$index]}=${profile_values[$value_index]}")
done

"$terraform_bin" -chdir="$terraform_dir" init -input=false -reconfigure \
  -backend-config="bucket=$state_bucket"
"$terraform_bin" -chdir="$terraform_dir" fmt -recursive -check
"$terraform_bin" -chdir="$terraform_dir" validate

plan_release() {
  local desired_backend="$1"
  local desired_frontend="$2"
  local output_plan="$3"
  local status

  set +e
  "$terraform_bin" -chdir="$terraform_dir" plan -input=false -no-color \
    -detailed-exitcode -out="$output_plan" \
    "-var=backend_image=$desired_backend" \
    "-var=frontend_image=$desired_frontend" \
    "${terraform_vars[@]}"
  status=$?
  set -e
  if [[ "$status" != 0 && "$status" != 2 ]]; then
    return "$status"
  fi

  "$terraform_bin" -chdir="$terraform_dir" show -json "$output_plan" |
    python3 -c '
import json
import sys

allowed = {
    "kubernetes_deployment_v1.api",
    "kubernetes_deployment_v1.worker",
    "kubernetes_deployment_v1.dispatcher",
    "kubernetes_deployment_v1.frontend",
}
plan = json.load(sys.stdin)
changes = []
rejected = []
for item in plan.get("resource_changes", []):
    actions = item.get("change", {}).get("actions", [])
    if actions == ["no-op"]:
        continue
    address = item.get("address", "unknown")
    changes.append(address)
    if address not in allowed or actions != ["update"]:
        rejected.append(f"{address}:{actions}")
if rejected:
    print("Unexpected Terraform release changes: " + ", ".join(rejected), file=sys.stderr)
    raise SystemExit(1)
print(f"release_plan_changes={len(changes)}")
'
}

verify_release() {
  local expected_status="$1"
  local attempt
  local response
  local deployment
  for deployment in creativeops-api creativeops-worker creativeops-dispatcher creativeops-frontend; do
    "${kubectl_args[@]}" rollout status "deployment/$deployment" --timeout=180s
  done

  for ((attempt = 1; attempt <= health_attempts; attempt++)); do
    response=""
    if response="$(curl -fsS --max-time 20 "$health_url" 2>/dev/null)"; then
      if printf '%s' "$response" |
        EXPECTED_VERTEX_STATUS="$expected_status" python3 -c '
import json
import os
import sys

payload = json.load(sys.stdin)
expected = os.environ["EXPECTED_VERTEX_STATUS"]
actual = payload.get("vertex", {}).get("status")
if payload.get("ok") is not True or payload.get("ready") is not True:
    raise SystemExit("Health response is not ready")
if payload.get("db") != "up" or actual != expected:
    raise SystemExit(f"Health dependency mismatch: db={payload.get(chr(100)+chr(98))}, vertex={actual}")
print(f"release_health_ready=true vertex_status={actual}")
' 2>/dev/null; then
        return 0
      fi
    fi
    if ((attempt < health_attempts)); then
      sleep "$health_interval_sec"
    fi
  done

  echo "Release health did not converge after $health_attempts attempts." >&2
  return 1
}

plan_release "$backend_image" "$frontend_image" "$plan_file"
if [[ "$plan_only" == true ]]; then
  echo "release_plan_only=true"
  exit 0
fi

set +e
"$terraform_bin" -chdir="$terraform_dir" apply -auto-approve "$plan_file"
apply_status=$?
set -e

verification_status=0
if [[ "$apply_status" == 0 ]]; then
  set +e
  verify_release "$expected_vertex_status"
  verification_status=$?
  set -e
else
  verification_status=$apply_status
fi

if [[ "$verification_status" != 0 ]]; then
  echo "Candidate verification failed; starting automatic Terraform rollback." >&2
  plan_release "$previous_backend" "$previous_frontend" "$rollback_plan_file"
  "$terraform_bin" -chdir="$terraform_dir" apply -auto-approve "$rollback_plan_file"
  verify_release "$recovery_vertex_status"
  echo "automatic_rollback_complete=true" >&2
  exit 1
fi

echo "release_complete=true"
