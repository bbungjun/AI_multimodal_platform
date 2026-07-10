from __future__ import annotations

import httpx
from fastapi import Request
from prometheus_client.parser import text_string_to_metric_families

from app.api import health as health_api
from app.main import app
from app.services.ops.prometheus import render_prometheus_metrics
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


def test_runtime_metrics_collapse_unmatched_paths_to_bounded_label():
    metrics = RuntimeMetrics()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/not-found/user-controlled-value",
            "raw_path": b"/not-found/user-controlled-value",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("test", 80),
            "client": ("127.0.0.1", 1234),
        }
    )

    assert metrics.path_for_request(request) == "unmatched"


def test_runtime_metrics_render_valid_prometheus_families():
    metrics = RuntimeMetrics()
    metrics.record_http_request(
        method="POST",
        path="/api/prompts/enhance",
        status_code=200,
        duration_ms=12.5,
    )
    metrics.record_http_request(
        method="POST",
        path="/api/prompts/enhance",
        status_code=502,
        duration_ms=37.5,
    )
    metrics.record_provider_failure(
        code="prompt_enhancement_invalid_response",
        status_code=None,
        retryable=False,
    )

    rendered = render_prometheus_metrics(metrics).decode("utf-8")
    families = {
        family.name: family
        for family in text_string_to_metric_families(rendered)
    }

    request_samples = {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for sample in families["creativeops_http_requests"].samples
    }
    assert request_samples[
        (
            "creativeops_http_requests_total",
            (
                ("method", "POST"),
                ("path", "/api/prompts/enhance"),
                ("status", "200"),
            ),
        )
    ] == 1
    assert request_samples[
        (
            "creativeops_http_requests_total",
            (
                ("method", "POST"),
                ("path", "/api/prompts/enhance"),
                ("status", "502"),
            ),
        )
    ] == 1

    duration_samples = {
        sample.name: sample.value
        for sample in families[
            "creativeops_http_request_duration_milliseconds"
        ].samples
    }
    assert duration_samples[
        "creativeops_http_request_duration_milliseconds_count"
    ] == 2
    assert duration_samples[
        "creativeops_http_request_duration_milliseconds_sum"
    ] == 50.0

    provider_sample = next(
        sample
        for sample in families["creativeops_provider_failures"].samples
        if sample.name == "creativeops_provider_failures_total"
    )
    assert provider_sample.labels == {
        "code": "prompt_enhancement_invalid_response",
        "status": "none",
        "retryable": "false",
    }
    assert provider_sample.value == 1


def test_runtime_metrics_seed_provider_failure_series_before_first_failure():
    rendered = render_prometheus_metrics(RuntimeMetrics()).decode("utf-8")
    families = {
        family.name: family
        for family in text_string_to_metric_families(rendered)
    }
    samples = [
        sample
        for sample in families["creativeops_provider_failures"].samples
        if sample.name == "creativeops_provider_failures_total"
    ]

    assert {sample.labels["code"] for sample in samples} == {
        "prompt_enhancement_invalid_response",
        "vertex_rate_limited",
        "vertex_request_invalid",
        "vertex_transient_error",
    }
    assert all(sample.value == 0 for sample in samples)


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


async def test_prometheus_metrics_endpoint_uses_standard_content_type(monkeypatch):
    runtime_metrics.reset()
    monkeypatch.setattr(health_api, "check_db_connection", _db_up)
    monkeypatch.setattr(health_api, "get_vertex_readiness", _vertex_ready)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            await client.get("/api/health")
            response = await client.get("/metrics")
    finally:
        runtime_metrics.reset()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain;")
    assert "version=" in response.headers["content-type"]
    assert 'path="/api/health"' in response.text
    assert "creativeops_http_requests_total" in response.text
