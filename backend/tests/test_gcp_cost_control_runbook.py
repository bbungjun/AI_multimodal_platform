from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GCP_RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/gcp-gke.md"
GCP_README_PATH = REPO_ROOT / "infra/gcp/README.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def test_gcp_runbook_documents_temporary_pause_cost_boundary():
    runbook = _text(GCP_RUNBOOK_PATH)
    runbook_one_line = _one_line(runbook)

    assert "temporary demo pause" in runbook
    assert '-var "api_replicas=0"' in runbook
    assert '-var "frontend_replicas=0"' in runbook
    assert '-var "worker_replicas=0"' in runbook
    assert '-var "dispatcher_replicas=0"' in runbook
    assert '-var "node_count=0"' in runbook
    assert '-var "ai_provider=mock"' in runbook
    assert "no running API, frontend, worker, or dispatcher pods" in runbook
    assert "frontend `LoadBalancer` service" in runbook
    assert "may still incur cost" in runbook_one_line


def test_gcp_readme_distinguishes_pause_from_full_teardown():
    readme = _text(GCP_README_PATH)
    readme_one_line = _one_line(readme)

    assert "## Cost-Control Boundary" in readme
    assert "`node_count=0`" in readme
    assert "GKE worker VMs" in readme_one_line
    assert "Cloud SQL" in readme
    assert "Redis" in readme
    assert (
        "Use Terraform `destroy` only when full teardown is intended"
        in readme_one_line
    )
