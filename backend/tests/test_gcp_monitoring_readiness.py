from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APIS_PATH = REPO_ROOT / "infra/gcp/apis.tf"
GKE_PATH = REPO_ROOT / "infra/gcp/gke.tf"
MONITORING_PATH = REPO_ROOT / "infra/gcp/monitoring.tf"
VARIABLES_PATH = REPO_ROOT / "infra/gcp/variables.tf"
WORKLOADS_PATH = REPO_ROOT / "infra/gcp/k8s-workloads.tf"
GCP_RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/gcp-gke.md"
GCP_README_PATH = REPO_ROOT / "infra/gcp/README.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def test_managed_prometheus_collection_targets_named_api_port():
    apis = _text(APIS_PATH)
    gke = _one_line(_text(GKE_PATH))
    monitoring = _one_line(_text(MONITORING_PATH))
    workloads = _one_line(_text(WORKLOADS_PATH))

    assert '"monitoring.googleapis.com"' in apis
    assert "monitoring_config { managed_prometheus { enabled = true" in gke
    assert 'kind = "PodMonitoring"' in monitoring
    assert 'namespace = kubernetes_namespace_v1.app.metadata[0].name' in monitoring
    assert 'app = "creativeops-api"' in monitoring
    assert 'port = "metrics"' in monitoring
    assert 'path = "/metrics"' in monitoring
    assert 'interval = "30s"' in monitoring
    assert 'name = "metrics" container_port = 8000' in workloads


def test_alert_policies_are_opt_in_and_use_bounded_promql_windows():
    variables = _one_line(_text(VARIABLES_PATH))
    monitoring = _one_line(_text(MONITORING_PATH))

    assert 'variable "monitoring_alerts_enabled"' in variables
    assert 'variable "monitoring_notification_channel_names"' in variables
    assert 'variable "monitoring_http_5xx_error_rate_threshold"' in variables
    assert 'variable "monitoring_http_min_requests_per_window"' in variables
    assert 'variable "monitoring_provider_failures_per_window"' in variables
    assert "monitoring_alerts_enabled ? 1 : 0" in monitoring
    assert "creativeops_http_requests_total" in monitoring
    assert 'status=~"5.."' in monitoring
    assert 'path!~"/metrics|/api/health|/api/health/live|unmatched"' in monitoring
    assert "[5m]" in monitoring
    assert "monitoring_http_min_requests_per_window" in monitoring
    assert "creativeops_provider_failures_total" in monitoring
    assert "sum by (code)" in monitoring
    assert (
        "notification_channels = var.monitoring_notification_channel_names"
        in monitoring
    )


def test_monitoring_docs_keep_enablement_and_rollback_explicit():
    runbook = _one_line(_text(GCP_RUNBOOK_PATH))
    readme = _one_line(_text(GCP_README_PATH))

    assert "Managed Prometheus And Alert Readiness" in runbook
    assert "monitoring_alerts_enabled=false" in runbook
    assert "monitoring_alerts_enabled=true" in runbook
    assert "kubectl get podmonitoring" in runbook
    assert "notification channel" in runbook
    assert "Managed Prometheus Boundary" in readme
    assert "disabled by default" in readme
