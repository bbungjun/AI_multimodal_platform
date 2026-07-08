from __future__ import annotations

import httpx

from app.api import health as health_api
from app.main import app
from app.services.ops.runtime import RuntimeMetrics, runtime_metrics
from app.services.vertex.client import VertexReadiness


async def _db_up() -> bool:
    return True


def _vertex_ready() -> VertexReadiness:
    return VertexReadiness(
        ready=True,
        status="ready",
        credentials="available",
        project="configured",
        location="us-central1",
    )


def test_runtime_metrics_records_http_and_provider_failure_snapshots():
    metrics = RuntimeMetrics()

    metrics.record_http_request(
        method="get",
        path="/api/health",
        status_code=200,
        duration_ms=10.0,
    )
    metrics.record_http_request(
        method="GET",
        path="/api/health",
        status_code=503,
        duration_ms=30.0,
    )
    metrics.record_provider_failure(
        code="vertex_rate_limited",
        status_code=429,
        retryable=True,
    )
    metrics.record_provider_failure(
        code="prompt_enhancement_invalid_response",
        status_code=None,
        retryable=False,
    )

    snapshot = metrics.snapshot()

    assert snapshot.http.requests_total == 2
    assert snapshot.http.errors_total == 1
    assert snapshot.http.error_rate == 0.5
    assert snapshot.http.endpoints[0].method == "GET"
    assert snapshot.http.endpoints[0].path == "/api/health"
    assert snapshot.http.endpoints[0].requests == 2
    assert snapshot.http.endpoints[0].status_counts == {"200": 1, "503": 1}
    assert snapshot.http.endpoints[0].latency_ms.avg_ms == 20.0
    assert snapshot.http.endpoints[0].latency_ms.p95_ms == 30.0
    assert snapshot.provider_failures.failures_total == 2
    assert snapshot.provider_failures.retryable == 1
    assert snapshot.provider_failures.non_retryable == 1
    assert snapshot.provider_failures.by_code == {
        "prompt_enhancement_invalid_response": 1,
        "vertex_rate_limited": 1,
    }
    assert snapshot.provider_failures.by_status == {"429": 1, "none": 1}


async def test_ops_metrics_endpoint_reports_recorded_route_template(monkeypatch):
    runtime_metrics.reset()
    monkeypatch.setattr(health_api, "check_db_connection", _db_up)
    monkeypatch.setattr(health_api, "get_vertex_readiness", _vertex_ready)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            health_response = await client.get("/api/health")
            metrics_response = await client.get("/api/ops/metrics")
    finally:
        runtime_metrics.reset()

    assert health_response.status_code == 200
    assert metrics_response.status_code == 200
    body = metrics_response.json()
    assert body["http"]["requests_total"] >= 1
    endpoint = next(
        item for item in body["http"]["endpoints"] if item["path"] == "/api/health"
    )
    assert endpoint["method"] == "GET"
    assert endpoint["requests"] == 1
    assert endpoint["status_counts"]["200"] == 1
