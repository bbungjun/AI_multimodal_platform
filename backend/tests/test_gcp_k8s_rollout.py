from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GKE_PATH = REPO_ROOT / "infra/gcp/gke.tf"
WORKLOADS_PATH = REPO_ROOT / "infra/gcp/k8s-workloads.tf"


def _gke_text() -> str:
    return GKE_PATH.read_text(encoding="utf-8")


def _workloads_text() -> str:
    return WORKLOADS_PATH.read_text(encoding="utf-8")


def _terraform_resource_block(
    terraform_text: str, resource_type: str, resource_name: str
) -> str:
    marker = f'resource "{resource_type}" "{resource_name}" {{'
    start = terraform_text.find(marker)
    assert start != -1, f"Expected Terraform resource {resource_name!r}."
    return _balanced_block(terraform_text, start + len(marker) - 1)


def _resource_block(terraform_text: str, resource_name: str) -> str:
    return _terraform_resource_block(
        terraform_text, "kubernetes_deployment_v1", resource_name
    )


def _balanced_block(terraform_text: str, opening_brace_index: int) -> str:
    depth = 0
    for index in range(opening_brace_index, len(terraform_text)):
        character = terraform_text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return terraform_text[opening_brace_index : index + 1]
    raise AssertionError(
        f"Expected balanced Terraform block from index {opening_brace_index}."
    )


def test_api_rollout_keeps_old_ready_pod_until_replacement_is_ready():
    api_block = _resource_block(_workloads_text(), "api")

    assert 'type = "RollingUpdate"' in api_block
    assert 'max_surge       = "1"' in api_block
    assert 'max_unavailable = "0"' in api_block
    assert "min_ready_seconds         = 5" in api_block
    assert "progress_deadline_seconds = 180" in api_block
    assert 'path = "/api/health"' in api_block
    assert 'path = "/api/health/live"' in api_block


def test_frontend_rollout_keeps_old_ready_pod_until_replacement_is_ready():
    frontend_block = _resource_block(_workloads_text(), "frontend")

    assert 'type = "RollingUpdate"' in frontend_block
    assert 'max_surge       = "1"' in frontend_block
    assert 'max_unavailable = "0"' in frontend_block
    assert "min_ready_seconds         = 5" in frontend_block
    assert "progress_deadline_seconds = 180" in frontend_block
    assert frontend_block.count('path = "/"') >= 2


def test_api_and_frontend_pdbs_only_exist_for_multi_replica_rollouts():
    workloads = _workloads_text()

    assert 'resource "kubernetes_pod_disruption_budget_v1" "api"' in workloads
    assert "count = var.api_replicas > 1 ? 1 : 0" in workloads
    assert 'resource "kubernetes_pod_disruption_budget_v1" "frontend"' in workloads
    assert "count = var.frontend_replicas > 1 ? 1 : 0" in workloads


def test_node_pool_requires_capacity_for_multi_replica_rollouts():
    node_pool_block = _terraform_resource_block(
        _gke_text(), "google_container_node_pool", "general"
    )

    assert "precondition" in node_pool_block
    assert "var.node_count >= 2" in node_pool_block
    assert "var.api_replicas <= 1" in node_pool_block
    assert "var.frontend_replicas <= 1" in node_pool_block
    assert "Set node_count >= 2" in node_pool_block
    assert "Insufficient cpu" in node_pool_block
