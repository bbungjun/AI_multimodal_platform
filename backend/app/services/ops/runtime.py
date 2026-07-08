from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import Request

from app.schemas import (
    OpsHttpEndpointMetricsResponse,
    OpsHttpRuntimeMetricsResponse,
    OpsLatencyMetricsResponse,
    OpsProviderFailureMetricsResponse,
    OpsRuntimeMetricsResponse,
)


RECENT_LATENCY_SAMPLE_SIZE = 512


@dataclass
class _EndpointStats:
    method: str
    path: str
    requests: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    status_counts: Counter[str] = field(default_factory=Counter)
    recent_latencies_ms: deque[float] = field(
        default_factory=lambda: deque(maxlen=RECENT_LATENCY_SAMPLE_SIZE),
    )

    def record(self, *, status_code: int, duration_ms: float) -> None:
        self.requests += 1
        if status_code >= 400:
            self.errors += 1
        self.total_latency_ms += duration_ms
        self.max_latency_ms = max(self.max_latency_ms, duration_ms)
        self.status_counts[str(status_code)] += 1
        self.recent_latencies_ms.append(duration_ms)

    def snapshot(self) -> OpsHttpEndpointMetricsResponse:
        latencies = list(self.recent_latencies_ms)
        return OpsHttpEndpointMetricsResponse(
            method=self.method,
            path=self.path,
            requests=self.requests,
            errors=self.errors,
            error_rate=_rate(self.errors, self.requests),
            status_counts=dict(sorted(self.status_counts.items())),
            latency_ms=OpsLatencyMetricsResponse(
                avg_ms=_round_ms(self.total_latency_ms / self.requests),
                p50_ms=_round_ms(_percentile(latencies, 50)),
                p95_ms=_round_ms(_percentile(latencies, 95)),
                max_ms=_round_ms(self.max_latency_ms),
                recent_samples=len(latencies),
            ),
        )


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._started_at = datetime.now(timezone.utc)
            self._started_monotonic = monotonic()
            self._endpoints: dict[tuple[str, str], _EndpointStats] = {}
            self._provider_failures_by_code: Counter[str] = Counter()
            self._provider_failures_by_status: Counter[str] = Counter()
            self._provider_retryable = 0
            self._provider_non_retryable = 0

    def path_for_request(self, request: Request) -> str:
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and route_path:
            return route_path
        return request.url.path or "unknown"

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        normalized_method = method.upper()
        normalized_path = path or "unknown"
        normalized_duration_ms = max(0.0, duration_ms)
        key = (normalized_method, normalized_path)
        with self._lock:
            endpoint = self._endpoints.get(key)
            if endpoint is None:
                endpoint = _EndpointStats(
                    method=normalized_method,
                    path=normalized_path,
                )
                self._endpoints[key] = endpoint
            endpoint.record(
                status_code=status_code,
                duration_ms=normalized_duration_ms,
            )

    def record_provider_failure(
        self,
        *,
        code: str,
        status_code: int | None,
        retryable: bool,
    ) -> None:
        normalized_code = code or "unknown"
        normalized_status = str(status_code) if status_code is not None else "none"
        with self._lock:
            self._provider_failures_by_code[normalized_code] += 1
            self._provider_failures_by_status[normalized_status] += 1
            if retryable:
                self._provider_retryable += 1
            else:
                self._provider_non_retryable += 1

    def snapshot(self) -> OpsRuntimeMetricsResponse:
        with self._lock:
            endpoint_snapshots = [
                endpoint.snapshot()
                for endpoint in sorted(
                    self._endpoints.values(),
                    key=lambda item: (item.path, item.method),
                )
            ]
            requests_total = sum(
                endpoint.requests for endpoint in self._endpoints.values()
            )
            errors_total = sum(endpoint.errors for endpoint in self._endpoints.values())
            provider_failures_total = sum(self._provider_failures_by_code.values())

            return OpsRuntimeMetricsResponse(
                http=OpsHttpRuntimeMetricsResponse(
                    started_at=self._started_at,
                    uptime_sec=round(max(0.0, monotonic() - self._started_monotonic), 2),
                    requests_total=requests_total,
                    errors_total=errors_total,
                    error_rate=_rate(errors_total, requests_total),
                    endpoints=endpoint_snapshots,
                ),
                provider_failures=OpsProviderFailureMetricsResponse(
                    failures_total=provider_failures_total,
                    retryable=self._provider_retryable,
                    non_retryable=self._provider_non_retryable,
                    by_code=dict(sorted(self._provider_failures_by_code.items())),
                    by_status=dict(sorted(self._provider_failures_by_status.items())),
                ),
            )


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = ceil((percentile / 100) * len(sorted_values)) - 1
    return sorted_values[min(max(index, 0), len(sorted_values) - 1)]


def _rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 6)


def _round_ms(value: float) -> float:
    return round(value, 2)


runtime_metrics = RuntimeMetrics()
