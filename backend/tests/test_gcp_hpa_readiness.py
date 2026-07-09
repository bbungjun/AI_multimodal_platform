from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HPA_PATH = REPO_ROOT / "infra/gcp/k8s-hpa.tf"
VARIABLES_PATH = REPO_ROOT / "infra/gcp/variables.tf"
WORKLOADS_PATH = REPO_ROOT / "infra/gcp/k8s-workloads.tf"
GCP_RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/gcp-gke.md"
GCP_README_PATH = REPO_ROOT / "infra/gcp/README.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _one_line(text: str) -> str:
    return " ".join(text.split())


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


def _terraform_resource_block(
    terraform_text: str, resource_type: str, resource_name: str
) -> str:
    marker = f'resource "{resource_type}" "{resource_name}" {{'
    start = terraform_text.find(marker)
    assert start != -1, f"Expected Terraform resource {resource_name!r}."
    return _balanced_block(terraform_text, start + len(marker) - 1)


def _variable_block(terraform_text: str, variable_name: str) -> str:
    marker = f'variable "{variable_name}" {{'
    start = terraform_text.find(marker)
    assert start != -1, f"Expected Terraform variable {variable_name!r}."
    return _balanced_block(terraform_text, start + len(marker) - 1)


def _deployment_block(terraform_text: str, deployment_name: str) -> str:
    return _terraform_resource_block(
        terraform_text, "kubernetes_deployment_v1", deployment_name
    )


def test_workload_hpa_variables_are_explicit_and_disabled_by_default():
    variables = _text(VARIABLES_PATH)

    for prefix in ("api", "frontend"):
        enabled = _variable_block(variables, f"{prefix}_hpa_enabled")
        min_replicas = _variable_block(variables, f"{prefix}_hpa_min_replicas")
        max_replicas = _variable_block(variables, f"{prefix}_hpa_max_replicas")
        cpu_target = _variable_block(
            variables, f"{prefix}_hpa_cpu_target_utilization"
        )

        assert "default     = false" in enabled
        assert "default     = 2" in min_replicas
        assert "default     = 4" in max_replicas
        assert "default     = 70" in cpu_target
        assert f"{prefix}_hpa_cpu_target_utilization >= 1" in cpu_target
        assert f"{prefix}_hpa_cpu_target_utilization <= 100" in cpu_target


def test_api_and_frontend_hpas_target_cpu_requested_workloads():
    hpa = _text(HPA_PATH)
    workloads = _text(WORKLOADS_PATH)

    api_hpa = _terraform_resource_block(
        hpa, "kubernetes_horizontal_pod_autoscaler_v2", "api"
    )
    frontend_hpa = _terraform_resource_block(
        hpa, "kubernetes_horizontal_pod_autoscaler_v2", "frontend"
    )
    api_deployment = _deployment_block(workloads, "api")
    frontend_deployment = _deployment_block(workloads, "frontend")

    assert "count = var.api_hpa_enabled ? 1 : 0" in api_hpa
    assert "name        = kubernetes_deployment_v1.api.metadata[0].name" in api_hpa
    assert "min_replicas = var.api_hpa_min_replicas" in api_hpa
    assert "max_replicas = var.api_hpa_max_replicas" in api_hpa
    assert 'type = "Resource"' in api_hpa
    assert 'name = "cpu"' in api_hpa
    assert "average_utilization = var.api_hpa_cpu_target_utilization" in api_hpa
    assert 'cpu    = "100m"' in api_deployment

    assert "count = var.frontend_hpa_enabled ? 1 : 0" in frontend_hpa
    assert (
        "name        = kubernetes_deployment_v1.frontend.metadata[0].name"
        in frontend_hpa
    )
    assert "min_replicas = var.frontend_hpa_min_replicas" in frontend_hpa
    assert "max_replicas = var.frontend_hpa_max_replicas" in frontend_hpa
    assert 'type = "Resource"' in frontend_hpa
    assert 'name = "cpu"' in frontend_hpa
    assert (
        "average_utilization = var.frontend_hpa_cpu_target_utilization"
        in frontend_hpa
    )
    assert 'cpu    = "100m"' in frontend_deployment


def test_hpa_preconditions_keep_replica_ownership_predictable():
    hpa_one_line = _one_line(_text(HPA_PATH))

    assert "api_hpa_min_replicas <= var.api_hpa_max_replicas" in hpa_one_line
    assert "var.api_replicas == var.api_hpa_min_replicas" in hpa_one_line
    assert "frontend_hpa_min_replicas <=" in hpa_one_line
    assert "var.frontend_replicas == var.frontend_hpa_min_replicas" in hpa_one_line
    assert "initial desired replica count matches the HPA floor" in hpa_one_line


def test_hpa_runbook_documents_operating_boundary_and_rollback():
    runbook = _one_line(_text(GCP_RUNBOOK_PATH))
    readme = _one_line(_text(GCP_README_PATH))

    assert "Workload HPA Readiness" in runbook
    assert "api_hpa_enabled=true" in runbook
    assert "frontend_hpa_enabled=true" in runbook
    assert "api_replicas=2" in runbook
    assert "api_hpa_min_replicas=2" in runbook
    assert "Terraform still declares the initial Deployment replica floor" in runbook
    assert "api_hpa_enabled=false" in runbook
    assert "Workload HPA Boundary" in readme
    assert "disabled by default" in readme
