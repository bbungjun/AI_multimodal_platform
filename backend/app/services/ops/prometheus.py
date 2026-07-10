from __future__ import annotations

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    SummaryMetricFamily,
)

from app.services.ops.runtime import RuntimeMetrics, runtime_metrics


class RuntimeMetricsCollector:
    def __init__(self, metrics: RuntimeMetrics) -> None:
        self._metrics = metrics

    def collect(self):
        snapshot = self._metrics.export()

        uptime = GaugeMetricFamily(
            "creativeops_runtime_uptime_seconds",
            "API process uptime in seconds.",
        )
        uptime.add_metric([], snapshot.uptime_sec)
        yield uptime

        requests = CounterMetricFamily(
            "creativeops_http_requests",
            "HTTP requests handled by the API process.",
            labels=["method", "path", "status"],
        )
        duration = SummaryMetricFamily(
            "creativeops_http_request_duration_milliseconds",
            "HTTP request duration observed by the API process in milliseconds.",
            labels=["method", "path"],
        )
        for endpoint in snapshot.endpoints:
            for status, count in endpoint.status_counts.items():
                requests.add_metric(
                    [endpoint.method, endpoint.path, status],
                    count,
                )
            duration.add_metric(
                [endpoint.method, endpoint.path],
                count_value=endpoint.requests,
                sum_value=endpoint.total_latency_ms,
            )
        yield requests
        yield duration

        provider_failures = CounterMetricFamily(
            "creativeops_provider_failures",
            "AI provider failures handled by the API process.",
            labels=["code", "status", "retryable"],
        )
        for (code, status, retryable), count in snapshot.provider_failures.items():
            provider_failures.add_metric(
                [code, status, str(retryable).lower()],
                count,
            )
        yield provider_failures


def render_prometheus_metrics(metrics: RuntimeMetrics = runtime_metrics) -> bytes:
    registry = CollectorRegistry(auto_describe=False)
    registry.register(RuntimeMetricsCollector(metrics))
    return generate_latest(registry)
