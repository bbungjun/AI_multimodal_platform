from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MONITORING_PATH = REPO_ROOT / "infra/gcp/monitoring.tf"
OUTPUTS_PATH = REPO_ROOT / "infra/gcp/outputs.tf"
VARIABLES_PATH = REPO_ROOT / "infra/gcp/variables.tf"
GCP_RUNBOOK_PATH = REPO_ROOT / "docs/runbooks/gcp-gke.md"
GCP_README_PATH = REPO_ROOT / "infra/gcp/README.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _one_line(text: str) -> str:
    return " ".join(text.split())


def test_dashboard_and_slo_are_opt_in_with_bounded_objectives():
    variables = _one_line(_text(VARIABLES_PATH))
    monitoring = _one_line(_text(MONITORING_PATH))

    assert 'variable "monitoring_dashboard_slo_enabled"' in variables
    assert 'variable "monitoring_availability_slo_goal"' in variables
    assert 'default = 0.995' in variables
    assert 'monitoring_availability_slo_goal <= 0.999' in variables
    assert 'variable "monitoring_availability_slo_rolling_days"' in variables
    assert 'default = 28' in variables
    assert 'monitoring_availability_slo_rolling_days <= 30' in variables
    assert "monitoring_dashboard_slo_enabled ? 1 : 0" in monitoring
    assert 'service_id = "creativeops-api"' in monitoring
    assert 'slo_id = "availability-28d"' in monitoring
    assert "goal = var.monitoring_availability_slo_goal" in monitoring
    assert (
        "rolling_period_days = var.monitoring_availability_slo_rolling_days"
        in monitoring
    )


def test_availability_sli_uses_prometheus_bad_and_total_counters():
    monitoring = _one_line(_text(MONITORING_PATH))

    assert (
        'metric.type=\\"prometheus.googleapis.com/'
        'creativeops_http_requests_total/counter\\"' in monitoring
    )
    assert 'resource.type=\\"prometheus_target\\"' in monitoring
    assert 'resource.label.\\"namespace\\"' in monitoring
    for excluded_path in (
        "/metrics",
        "/api/health",
        "/api/health/live",
        "/api/ops/metrics",
        "/api/ops/health",
        "unmatched",
    ):
        assert f'metric.label.\\"path\\"!=\\"{excluded_path}\\"' in monitoring
    assert "good_total_ratio" in monitoring
    assert 'metric.label.\\"status\\"=starts_with(\\"5\\")' in monitoring
    assert "total_service_filter = local.monitoring_request_metric_filter" in monitoring


def test_reliability_dashboard_covers_service_and_slo_signals():
    monitoring = _one_line(_text(MONITORING_PATH))
    outputs = _one_line(_text(OUTPUTS_PATH))

    assert 'displayName = "CreativeOps API Reliability"' in monitoring
    assert "Request throughput" in monitoring
    assert "HTTP 5xx ratio" in monitoring
    assert "HTTP request latency p95" in monitoring
    assert "histogram_quantile(0.95" in monitoring
    assert "Prompt provider failures by code" in monitoring
    assert "select_slo_compliance" in monitoring
    assert "select_slo_budget" in monitoring
    assert "select_slo_burn_rate" in monitoring
    assert "monitoring_dashboard_name" in outputs
    assert "monitoring_service_name" in outputs
    assert "monitoring_availability_slo_name" in outputs
    assert "try(google_monitoring_dashboard.reliability[0].id, null)" in outputs


def test_slo_docs_define_rollout_rollback_and_measurement_boundary():
    runbook = _one_line(_text(GCP_RUNBOOK_PATH))
    readme = _one_line(_text(GCP_README_PATH))

    assert "Dashboard And Availability SLO" in runbook
    assert "99.5%" in runbook
    assert "28-day" in runbook
    assert "monitoring_dashboard_slo_enabled=false" in runbook
    assert "monitoring_dashboard_slo_enabled=true" in runbook
    assert "burn rate" in runbook
    assert "all API pods" in runbook
    assert "Dashboard And SLO Boundary" in readme
    assert "application-observed requests" in readme
