from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "benchmark_mock_orchestration.py"
)


def load_benchmark_module():
    spec = importlib.util.spec_from_file_location(
        "benchmark_mock_orchestration",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_workload_is_20_warmup_100_steady_and_five_200_bursts():
    module = load_benchmark_module()

    phases = module.build_phase_specs()

    assert [(phase["name"], phase["jobs"], phase["submit_concurrency"]) for phase in phases] == [
        ("warmup", 20, 2),
        ("steady", 100, 2),
        ("burst-1", 200, 50),
        ("burst-2", 200, 50),
        ("burst-3", 200, 50),
        ("burst-4", 200, 50),
        ("burst-5", 200, 50),
    ]
    assert sum(phase["jobs"] for phase in phases) == 1120
    assert phases[0]["include_in_aggregate"] is False
    assert all(phase["include_in_aggregate"] for phase in phases[1:])


def test_percentile_uses_linear_interpolation_and_rejects_empty_input():
    module = load_benchmark_module()

    values = [10.0, 20.0, 30.0, 40.0]

    assert module.percentile(values, 0.50) == pytest.approx(25.0)
    assert module.percentile(values, 0.95) == pytest.approx(38.5)
    assert module.percentile(values, 0.99) == pytest.approx(39.7)
    with pytest.raises(module.BenchmarkError, match="empty"):
        module.percentile([], 0.95)


def test_analyze_completed_job_calculates_claim_execution_and_end_to_end_latency():
    module = load_benchmark_module()
    job = {
        "id": "job-1",
        "state": "completed",
        "attempts": 1,
        "created_at": "2026-07-27T01:00:00Z",
        "state_history": [
            {
                "state": "queued",
                "at": "2026-07-27T01:00:00.250000Z",
                "detail": {"runner": "celery"},
            },
            {
                "state": "generating",
                "at": "2026-07-27T01:00:00.300000Z",
                "detail": {"rate_limit_wait_sec": 0.0},
            },
            {
                "state": "downloading",
                "at": "2026-07-27T01:00:00.600000Z",
                "detail": {"image_count": 1},
            },
            {
                "state": "completed",
                "at": "2026-07-27T01:00:00.750000Z",
                "detail": None,
            },
        ],
        "error": None,
    }

    record = module.analyze_job(job, phase="steady", submit_latency_ms=12.5)

    assert record["runner"] == "celery"
    assert record["claim_latency_ms"] == pytest.approx(250.0)
    assert record["execution_latency_ms"] == pytest.approx(500.0)
    assert record["end_to_end_latency_ms"] == pytest.approx(750.0)
    assert record["submit_latency_ms"] == pytest.approx(12.5)
    assert record["rate_limit_wait_sec"] == pytest.approx(0.0)
    assert record["duplicate_execution"] is False


def test_analyze_job_marks_multiple_attempts_or_claims_as_duplicate_execution():
    module = load_benchmark_module()
    job = {
        "id": "job-duplicate",
        "state": "completed",
        "attempts": 2,
        "created_at": "2026-07-27T01:00:00Z",
        "state_history": [
            {"state": "queued", "at": "2026-07-27T01:00:00.100000Z"},
            {"state": "queued", "at": "2026-07-27T01:00:00.200000Z"},
            {"state": "completed", "at": "2026-07-27T01:00:00.500000Z"},
        ],
        "error": None,
    }

    record = module.analyze_job(job, phase="burst-1", submit_latency_ms=10)

    assert record["duplicate_execution"] is True
    assert record["queued_transition_count"] == 2


def test_validate_preflight_requires_mock_celery_and_sufficient_rate_limit():
    module = load_benchmark_module()
    health = {
        "ok": True,
        "ready": True,
        "db": "up",
        "vertex": {
            "status": "mock_provider",
            "credentials": "not_required",
        },
    }
    ops = {
        "ok": True,
        "db": "up",
        "dispatch": {"mode": "celery", "queue": "generation"},
    }
    worker_env = {
        "AI_PROVIDER": "mock",
        "JOB_DISPATCH_MODE": "celery",
        "RATE_LIMIT_IMAGEN_PER_MIN": "5000",
        "CELERY_WORKER_CONCURRENCY": "2",
        "CELERY_DEFAULT_QUEUE": "generation",
    }

    module.validate_preflight(
        health,
        ops,
        worker_env,
        expected_dispatch="celery",
        minimum_imagen_rate_limit=5000,
    )

    with pytest.raises(module.BenchmarkError, match="mock_provider"):
        module.validate_preflight(
            {**health, "vertex": {"status": "ready", "credentials": "adc"}},
            ops,
            worker_env,
            expected_dispatch="celery",
            minimum_imagen_rate_limit=5000,
        )
    with pytest.raises(module.BenchmarkError, match="dispatch mode"):
        module.validate_preflight(
            health,
            {**ops, "dispatch": {"mode": "in-process", "queue": None}},
            worker_env,
            expected_dispatch="celery",
            minimum_imagen_rate_limit=5000,
        )
    with pytest.raises(module.BenchmarkError, match="rate limit"):
        module.validate_preflight(
            health,
            ops,
            {**worker_env, "RATE_LIMIT_IMAGEN_PER_MIN": "5"},
            expected_dispatch="celery",
            minimum_imagen_rate_limit=5000,
        )


def test_validate_preflight_can_require_idle_jobs_and_outbox():
    module = load_benchmark_module()
    health = {
        "ok": True,
        "ready": True,
        "db": "up",
        "vertex": {
            "status": "mock_provider",
            "credentials": "not_required",
        },
    }
    ops = {
        "ok": True,
        "db": "up",
        "dispatch": {"mode": "celery"},
        "jobs": {"active": 1},
        "outbox": {"pending": 0},
    }

    with pytest.raises(module.BenchmarkError, match="idle"):
        module.validate_preflight(
            health,
            ops,
            None,
            expected_dispatch="celery",
            minimum_imagen_rate_limit=0,
            require_idle=True,
        )


def test_summarize_records_excludes_warmup_and_reports_latency_percentiles():
    module = load_benchmark_module()
    records = [
        {
            "phase": "warmup",
            "include_in_aggregate": False,
            "state": "completed",
            "submit_latency_ms": 999.0,
            "claim_latency_ms": 999.0,
            "execution_latency_ms": 999.0,
            "end_to_end_latency_ms": 999.0,
            "duplicate_execution": False,
            "rate_limit_wait_sec": 0.0,
            "created_at": "2026-07-27T01:00:00Z",
            "completed_at": "2026-07-27T01:00:01Z",
        },
        {
            "phase": "steady",
            "include_in_aggregate": True,
            "state": "completed",
            "submit_latency_ms": 10.0,
            "claim_latency_ms": 100.0,
            "execution_latency_ms": 200.0,
            "end_to_end_latency_ms": 300.0,
            "duplicate_execution": False,
            "rate_limit_wait_sec": 0.0,
            "created_at": "2026-07-27T01:00:02Z",
            "completed_at": "2026-07-27T01:00:02.300000Z",
        },
        {
            "phase": "burst-1",
            "include_in_aggregate": True,
            "state": "completed",
            "submit_latency_ms": 20.0,
            "claim_latency_ms": 200.0,
            "execution_latency_ms": 400.0,
            "end_to_end_latency_ms": 600.0,
            "duplicate_execution": True,
            "rate_limit_wait_sec": 0.25,
            "created_at": "2026-07-27T01:00:03Z",
            "completed_at": "2026-07-27T01:00:03.600000Z",
        },
    ]

    summary = module.summarize_records(records)

    assert summary["jobs"] == 2
    assert summary["completed"] == 2
    assert summary["failed"] == 0
    assert summary["duplicate_execution"] == 1
    assert summary["rate_limit_wait"]["jobs"] == 1
    assert summary["rate_limit_wait"]["max_sec"] == pytest.approx(0.25)
    assert summary["latency_ms"]["claim"]["p50"] == pytest.approx(150.0)
    assert summary["latency_ms"]["end_to_end"]["p95"] == pytest.approx(585.0)
    assert summary["throughput_jobs_sec"] == pytest.approx(1.25)


def test_parse_kubectl_top_normalizes_cpu_and_memory_without_other_namespaces():
    module = load_benchmark_module()
    output = "\n".join(
        [
            "creativeops-api-abc api 125m 256Mi",
            "creativeops-worker-def worker 0.5 1Gi",
            "unrelated-pod app 50m 64Mi",
        ]
    )

    samples = module.parse_kubectl_top(
        output,
        workload_prefixes=("creativeops-api-", "creativeops-worker-"),
    )

    assert samples == [
        {
            "pod": "creativeops-api-abc",
            "container": "api",
            "cpu_millicores": 125.0,
            "memory_bytes": 256 * 1024 * 1024,
        },
        {
            "pod": "creativeops-worker-def",
            "container": "worker",
            "cpu_millicores": 500.0,
            "memory_bytes": 1024 * 1024 * 1024,
        },
    ]


def test_resource_summary_uses_peak_sum_across_replicas_per_container():
    module = load_benchmark_module()
    samples = [
        {
            "celery_queue_depth": 10,
            "active_jobs": 12,
            "outbox_pending": 4,
            "resources": [
                {
                    "pod": "creativeops-api-a",
                    "container": "api",
                    "cpu_millicores": 100.0,
                    "memory_bytes": 200,
                },
                {
                    "pod": "creativeops-api-b",
                    "container": "api",
                    "cpu_millicores": 150.0,
                    "memory_bytes": 300,
                },
                {
                    "pod": "creativeops-worker-a",
                    "container": "worker",
                    "cpu_millicores": 500.0,
                    "memory_bytes": 600,
                },
            ],
        },
        {
            "celery_queue_depth": 7,
            "active_jobs": 8,
            "outbox_pending": 1,
            "resources": [
                {
                    "pod": "creativeops-api-a",
                    "container": "api",
                    "cpu_millicores": 200.0,
                    "memory_bytes": 250,
                },
                {
                    "pod": "creativeops-api-b",
                    "container": "api",
                    "cpu_millicores": 200.0,
                    "memory_bytes": 350,
                },
            ],
        },
    ]

    summary = module._resource_summary(samples)

    assert summary["peak_celery_queue_depth"] == 10
    assert summary["peak_active_jobs"] == 12
    assert summary["peak_outbox_pending"] == 4
    assert summary["peak_by_container"]["api"] == {
        "cpu_millicores": 400.0,
        "memory_bytes": 600,
    }
    assert summary["peak_by_container"]["worker"] == {
        "cpu_millicores": 500.0,
        "memory_bytes": 600,
    }


def test_whitelist_worker_environment_never_includes_broker_or_credentials():
    module = load_benchmark_module()
    values = {
        "AI_PROVIDER": "mock",
        "JOB_DISPATCH_MODE": "celery",
        "RATE_LIMIT_IMAGEN_PER_MIN": "5000",
        "CELERY_WORKER_CONCURRENCY": "2",
        "CELERY_DEFAULT_QUEUE": "generation",
        "CELERY_BROKER_URL": "redis://private-host:6379/0",
        "GOOGLE_APPLICATION_CREDENTIALS": "/opaque/credential.json",
    }

    assert module.whitelist_worker_environment(values) == {
        "AI_PROVIDER": "mock",
        "JOB_DISPATCH_MODE": "celery",
        "RATE_LIMIT_IMAGEN_PER_MIN": "5000",
        "CELERY_WORKER_CONCURRENCY": "2",
        "CELERY_DEFAULT_QUEUE": "generation",
    }


def test_iso_timestamp_accepts_z_and_returns_utc_datetime():
    module = load_benchmark_module()

    parsed = module.parse_timestamp("2026-07-27T01:00:00Z")

    assert parsed == datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
