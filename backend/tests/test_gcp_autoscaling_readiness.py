from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GKE_PATH = REPO_ROOT / "infra/gcp/gke.tf"
VARIABLES_PATH = REPO_ROOT / "infra/gcp/variables.tf"
GCP_RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/gcp-gke.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def test_node_pool_autoscaling_is_explicit_and_disabled_by_default():
    variables = _text(VARIABLES_PATH)
    gke = _text(GKE_PATH)

    assert 'variable "node_pool_autoscaling_enabled"' in variables
    assert "default     = false" in variables
    assert 'variable "node_pool_autoscaling_min_count"' in variables
    assert 'variable "node_pool_autoscaling_max_count"' in variables
    assert 'dynamic "autoscaling"' in gke
    assert "for_each = var.node_pool_autoscaling_enabled ? [1] : []" in gke
    assert "min_node_count = var.node_pool_autoscaling_min_count" in gke
    assert "max_node_count = var.node_pool_autoscaling_max_count" in gke


def test_node_pool_autoscaling_precondition_catches_invalid_bounds():
    gke_one_line = _one_line(_text(GKE_PATH))

    assert "node_pool_autoscaling_min_count <=" in gke_one_line
    assert "node_pool_autoscaling_max_count" in gke_one_line
    assert "node_pool_autoscaling_enabled is true" in gke_one_line


def test_runbook_keeps_autoscaling_as_no_apply_readiness_work():
    runbook_one_line = _one_line(_text(GCP_RUNBOOK_PATH))

    assert "Autoscaling Readiness" in runbook_one_line
    assert "Do not enable autoscaling on the live stack as a side effect" in runbook_one_line
    assert "temporary demo pause" in runbook_one_line
    assert "node_count=2" in runbook_one_line
    assert "k6 readiness profile" in runbook_one_line
