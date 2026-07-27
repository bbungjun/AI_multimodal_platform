from __future__ import annotations

import importlib.util
import json
import subprocess
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


def test_submit_phase_collects_all_successes_and_failures_without_early_abort():
    module = load_benchmark_module()

    class FakeClient:
        def request_json(self, method, path, *, expected_status, payload=None):
            assert method == "POST"
            assert path == "/api/generations"
            index = int(payload["prompt"].rsplit(" ", 1)[-1])
            if index == 2:
                raise module.BenchmarkError("HTTP 500")
            return {
                "id": f"job-{index}",
                "state": "pending",
                "created_at": "2026-07-27T01:00:00Z",
            }

    result = module.submit_phase(
        FakeClient(),
        run_id="run-1",
        phase={
            "name": "burst-1",
            "jobs": 3,
            "submit_concurrency": 3,
            "include_in_aggregate": True,
        },
    )

    assert sorted(result["submitted"]) == ["job-1", "job-3"]
    assert result["failures"] == [
        {
            "phase": "burst-1",
            "index": 2,
            "error": "HTTP 500",
        }
    ]


def test_http_client_normalizes_direct_timeout_as_ambiguous_submission(monkeypatch):
    module = load_benchmark_module()

    def raise_timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(module, "urlopen", raise_timeout)

    with pytest.raises(module.AmbiguousSubmissionError, match="timed out"):
        module.HttpClient("http://example.test").request_json(
            "POST",
            "/api/generations",
            expected_status=201,
            payload={"prompt": "benchmark run-1 steady 0001"},
        )


def test_command_output_normalizes_subprocess_timeout(monkeypatch):
    module = load_benchmark_module()

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["kubectl", "top"], timeout=15)

    monkeypatch.setattr(module.subprocess, "run", raise_timeout)

    with pytest.raises(module.BenchmarkError, match="timed out"):
        module._command_output(["kubectl", "top"], timeout_sec=15)


def test_command_output_normalizes_missing_executable(monkeypatch):
    module = load_benchmark_module()

    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("kubectl was not found")

    monkeypatch.setattr(module.subprocess, "run", raise_missing)

    with pytest.raises(module.BenchmarkError, match="could not start"):
        module._command_output(["kubectl", "top"])


def test_gke_target_guard_binds_base_url_and_dispatch_to_release_profile():
    module = load_benchmark_module()
    profile = {
        "health_url": "http://34.50.26.152/api/health",
        "expected_dispatch": "celery",
    }

    module.validate_gke_target(
        profile,
        base_url="http://34.50.26.152/",
        expected_dispatch="celery",
    )

    with pytest.raises(module.BenchmarkError, match="base URL"):
        module.validate_gke_target(
            profile,
            base_url="http://127.0.0.1:8000",
            expected_dispatch="celery",
        )
    with pytest.raises(module.BenchmarkError, match="dispatch"):
        module.validate_gke_target(
            profile,
            base_url="http://34.50.26.152",
            expected_dispatch="in-process",
        )


def test_kube_context_guard_requires_profile_cluster():
    module = load_benchmark_module()
    profile = {
        "project_id": "krafton-vertex-live-3108",
        "cluster_zone": "asia-northeast3-a",
        "cluster_name": "creativeops-portfolio",
    }
    expected = (
        "gke_krafton-vertex-live-3108_"
        "asia-northeast3-a_creativeops-portfolio"
    )
    config = {
        "current-context": expected,
        "contexts": [{"name": expected, "context": {"cluster": expected}}],
        "clusters": [{"name": expected, "cluster": {"server": "https://example.test"}}],
    }

    assert module.validate_kube_context(profile, config) == expected

    wrong = json.loads(json.dumps(config))
    wrong["contexts"][0]["context"]["cluster"] = "gke_other_project_zone_cluster"
    with pytest.raises(module.BenchmarkError, match="kubectl context"):
        module.validate_kube_context(profile, wrong)


def test_discover_run_jobs_paginates_and_matches_exact_prompt_prefix():
    module = load_benchmark_module()

    class FakeClient:
        def request_json(self, method, path, *, expected_status, payload=None):
            assert method == "GET"
            if "offset=0" in path:
                return [
                    {
                        "id": f"other-{index}",
                        "prompt": "not this benchmark",
                    }
                    for index in range(100)
                ]
            if "offset=100" in path:
                return [
                    {
                        "id": "job-1",
                        "prompt": "benchmark run-1 steady 0001",
                    },
                    {
                        "id": "job-other-run",
                        "prompt": "benchmark run-10 steady 0001",
                    },
                ]
            raise AssertionError(path)

    discovered = module.discover_run_jobs(
        FakeClient(),
        run_id="run-1",
        max_pages=3,
    )

    assert discovered == {
        "job-1": {
            "id": "job-1",
            "prompt": "benchmark run-1 steady 0001",
        }
    }


def test_run_id_rejects_whitespace_that_would_make_reconciliation_ambiguous():
    module = load_benchmark_module()

    assert module.validate_run_id("redis-celery-20260727T0626Z") == (
        "redis-celery-20260727T0626Z"
    )
    with pytest.raises(module.BenchmarkError, match="run-id"):
        module.validate_run_id("run 1")


def test_poll_jobs_reports_timeout_without_making_a_request(monkeypatch):
    module = load_benchmark_module()
    monotonic_values = iter([0.0, 2.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))

    class FakeClient:
        def request_json(self, *args, **kwargs):
            raise AssertionError("request should not be made after deadline")

    with pytest.raises(module.BenchmarkError, match="Timed out"):
        module.poll_jobs(
            FakeClient(),
            job_ids={"job-1"},
            timeout_sec=1,
            interval_sec=0,
        )


def test_cleanup_collects_unexpected_client_errors_instead_of_aborting():
    module = load_benchmark_module()

    class FakeClient:
        def request_json(self, method, path, *, expected_status, payload=None):
            if path.endswith("job-2"):
                raise RuntimeError("unexpected disconnect")
            return {}

    failures = module.cleanup_jobs(
        FakeClient(),
        ["job-1", "job-2", "job-3"],
        concurrency=3,
    )

    assert failures == [
        {
            "job_id": "job-2",
            "error": "unexpected disconnect",
        }
    ]


def test_sampler_records_command_timeout_as_sample_error(monkeypatch):
    module = load_benchmark_module()

    def raise_timeout(*args, **kwargs):
        raise module.BenchmarkError("Command timed out")

    monkeypatch.setattr(module, "_command_output", raise_timeout)
    sampler = module.GkeSampler(
        client=object(),
        kubectl="kubectl",
        namespace="creativeops-portfolio",
        worker_pod="worker-1",
        interval_sec=1,
    )

    sample = sampler.sample_once()

    assert sample["sample_error"] == "Command timed out"


def test_run_benchmark_writes_partial_report_after_keyboard_interrupt(
    monkeypatch,
    tmp_path,
):
    module = load_benchmark_module()
    output = tmp_path / "partial.json"
    args = module.build_parser().parse_args(
        [
            "--execute",
            "--output",
            str(output),
            "--warmup-jobs",
            "1",
            "--steady-jobs",
            "1",
            "--burst-jobs",
            "1",
            "--burst-rounds",
            "1",
        ]
    )

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def request_json(self, method, path, *, expected_status, payload=None):
            if path == "/api/health":
                return {
                    "ok": True,
                    "ready": True,
                    "db": "up",
                    "vertex": {
                        "status": "mock_provider",
                        "credentials": "not_required",
                    },
                }
            if path == "/api/ops/health":
                return {
                    "ok": True,
                    "db": "up",
                    "dispatch": {"mode": "celery"},
                    "jobs": {"active": 0},
                    "outbox": {"pending": 0},
                }
            if path.startswith("/api/generations?"):
                return []
            raise AssertionError(path)

    monkeypatch.setattr(module, "HttpClient", FakeClient)
    monkeypatch.setattr(
        module,
        "submit_phase",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        module.run_benchmark(args)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["run_error"] == "KeyboardInterrupt"
    assert report["completed_at"] is not None
    assert report["reconciliation"]["attempted"] is True


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


def test_parser_defaults_cleanup_to_low_db_safe_concurrency():
    module = load_benchmark_module()

    args = module.build_parser().parse_args([])

    assert args.cleanup_concurrency == 2


def test_iso_timestamp_accepts_z_and_returns_utc_datetime():
    module = load_benchmark_module()

    parsed = module.parse_timestamp("2026-07-27T01:00:00Z")

    assert parsed == datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
