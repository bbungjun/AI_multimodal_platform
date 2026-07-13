from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import generate_pairs
from generate_pairs import (
    EvaluationRunnerError,
    GenerationFailedError,
    RunnerConfig,
    arm_orders_for_cases,
    require_mock_provider,
    run_pairs,
    validate_mock_env_file,
)
from schemas import (
    ArmOrder,
    ArmStatus,
    BackendArtifactState,
    BenchmarkCase,
    BenchmarkCategory,
    BenchmarkLanguage,
    CreativityPreset,
    CleanupPolicy,
    EvidenceKind,
    MetricAdapterConfig,
    MetricName,
    ProviderMode,
    RunLifecycle,
    StatisticsConfig,
    file_sha256,
    load_benchmark_cases,
    load_cleanup_record,
    load_run_manifest,
    prompt_sha256,
    write_benchmark_cases,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class IncrementingClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 13, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class FakeEvaluationClient:
    def __init__(
        self,
        *,
        provider_status: str = "mock_provider",
        provider_retry_max_attempts: int = 3,
        fail_prompt_fragment: str | None = None,
        interrupt_next_poll: bool = False,
    ) -> None:
        self.provider_status = provider_status
        self.provider_retry_max_attempts = provider_retry_max_attempts
        self.fail_prompt_fragment = fail_prompt_fragment
        self.interrupt_next_poll = interrupt_next_poll
        self.calls: list[tuple[str, str]] = []
        self.created_payloads: list[dict[str, Any]] = []
        self.enhancement_payloads: list[dict[str, Any]] = []
        self.deleted_job_ids: list[str] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.file_bodies: dict[str, bytes] = {}

    def request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        step_name: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        del expected_status, step_name, headers
        self.calls.append((method, path))

        if method == "GET" and path == "/api/health":
            vertex_ready = self.provider_status == "ready"
            return {
                "ok": True,
                "ready": True,
                "db": "up",
                "provider_retry_max_attempts": self.provider_retry_max_attempts,
                "vertex": {
                    "status": self.provider_status,
                    "credentials": "available" if vertex_ready else "not_required",
                    "project": "configured" if vertex_ready else "not_required",
                },
            }

        if method == "POST" and path == "/api/prompts/enhance":
            assert payload is not None
            self.enhancement_payloads.append(deepcopy(payload))
            enhancement_id = f"enhancement-{len(self.enhancement_payloads)}"
            return {
                "id": enhancement_id,
                "original": payload["prompt"],
                "enhanced": f"{payload['prompt']} [mock enhanced]",
                "components": {"provider": "mock"},
                "target_mode": payload["target_mode"],
                "target_model": payload["target_model"],
                "llm_model": "gemini-2.5-flash",
                "template_version": "v1",
                "creativity_preset": payload["creativity_preset"],
            }

        if method == "POST" and path == "/api/generations":
            assert payload is not None
            self.created_payloads.append(deepcopy(payload))
            job_id = f"job-{len(self.created_payloads)}"
            parameters: dict[str, Any] = {
                "aspect_ratio": payload["aspect_ratio"],
                "number_of_images": payload["number_of_images"],
            }
            if payload.get("enhancement_id"):
                parameters["prompt_provenance"] = {
                    "source": "enhancement",
                    "enhancement_id": payload["enhancement_id"],
                    "execution_prompt_sha256": prompt_sha256(payload["prompt"]),
                }
            job = {
                "id": job_id,
                "mode": "t2i",
                "model": payload["model"],
                "state": "pending",
                "prompt": payload["prompt"],
                "execution_prompt_sha256": prompt_sha256(payload["prompt"]),
                "enhancement_id": payload.get("enhancement_id"),
                "attempts": 0,
                "parameters": parameters,
                "error": None,
                "assets": [],
            }
            self.jobs[job_id] = job
            return deepcopy(job)

        if method == "GET" and path.startswith("/api/generations/"):
            if self.interrupt_next_poll:
                self.interrupt_next_poll = False
                raise EvaluationRunnerError("simulated connection interruption")
            job_id = path.rsplit("/", 1)[-1]
            job = self.jobs[job_id]
            if self.fail_prompt_fragment and self.fail_prompt_fragment in job["prompt"]:
                failed = deepcopy(job)
                failed.update(
                    {
                        "state": "failed",
                        "attempts": 2,
                        "error": {
                            "code": "mock_generation_failed",
                            "message": "Controlled mock generation failure.",
                            "retryable": False,
                        },
                    }
                )
                self.jobs[job_id] = failed
                return deepcopy(failed)

            completed = deepcopy(job)
            completed["state"] = "completed"
            completed["attempts"] = 1
            completed_assets = []
            for index in range(int(job["parameters"]["number_of_images"])):
                asset_id = f"asset-{job_id}-{index}"
                file_url = f"/files/{job_id}/{index}.png"
                body = PNG_SIGNATURE + f"{job_id}:{index}".encode("utf-8")
                asset = {
                    "id": asset_id,
                    "job_id": job_id,
                    "kind": "image",
                    "local_path": f"{job_id}/{index}.png",
                    "mime": "image/png",
                    "size_bytes": len(body),
                    "url": file_url,
                }
                self.assets[asset_id] = asset
                self.file_bodies[file_url] = body
                completed_assets.append(asset)
            completed["assets"] = completed_assets
            self.jobs[job_id] = completed
            return deepcopy(completed)

        if method == "GET" and path.startswith("/api/assets/"):
            asset_id = path.rsplit("/", 1)[-1]
            return deepcopy(self.assets[asset_id])

        raise AssertionError(f"Unexpected JSON request: {method} {path}")

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | set[int],
        step_name: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str], int]:
        del expected_status, step_name, payload, headers
        self.calls.append((method, path))
        if method == "GET" and path in self.file_bodies:
            body = self.file_bodies[path]
            return body, {"Content-Type": "image/png"}, 200
        if method == "DELETE" and path.startswith("/api/generations/"):
            job_id = path.rsplit("/", 1)[-1]
            self.deleted_job_ids.append(job_id)
            return b"", {}, 204
        raise AssertionError(f"Unexpected byte request: {method} {path}")


def _benchmark_cases(count: int = 2, *, failing: bool = False) -> list[BenchmarkCase]:
    cases = []
    for index in range(count):
        prompt = f"prompt {index}"
        if failing and index == 0:
            prompt += " [[mock-fail:imagen]]"
        cases.append(
            BenchmarkCase(
                schema_version=1,
                case_id=f"case-{index}",
                source="test-fixture",
                language=BenchmarkLanguage.ENGLISH,
                category=BenchmarkCategory.SHORT_SUBJECT,
                original_prompt=prompt,
                evaluation_prompt=prompt,
                target_mode="t2i",
                target_model="imagen-4.0-fast-generate-001",
                creativity_preset=CreativityPreset.BALANCED,
                aspect_ratio="1:1",
                samples_per_arm=1,
                enabled=True,
            )
        )
    return cases


def _config(
    tmp_path: Path,
    cases: list[BenchmarkCase],
    *,
    run_id: str = "mock-run-001",
    keep_artifacts: bool = False,
) -> RunnerConfig:
    benchmark_path = tmp_path / "benchmark.v1.jsonl"
    write_benchmark_cases(benchmark_path, cases)
    return RunnerConfig(
        base_url="http://fake.test",
        benchmark_path=benchmark_path,
        runs_dir=tmp_path / "runs",
        run_id=run_id,
        keep_artifacts=keep_artifacts,
        poll_timeout_sec=1,
        poll_interval_sec=0,
        expected_enhancer_model="gemini-2.5-flash",
        expected_template_version="v1",
        git_sha="546a9b2",
        dirty_worktree=False,
    )


def test_arm_orders_are_stable_and_balanced_by_sorted_case_id():
    cases = list(reversed(_benchmark_cases(4)))

    orders = arm_orders_for_cases(cases)

    assert orders == {
        "case-0": ArmOrder.RAW_FIRST,
        "case-1": ArmOrder.ENHANCED_FIRST,
        "case-2": ArmOrder.RAW_FIRST,
        "case-3": ArmOrder.ENHANCED_FIRST,
    }


def test_controlled_failure_fixture_is_explicit_and_disabled_from_default_run():
    failure_cases = load_benchmark_cases(FIXTURES / "benchmark.failure.v1.jsonl")
    default_cases = load_benchmark_cases(FIXTURES / "benchmark.valid.v1.jsonl")

    assert len(failure_cases) == 1
    assert "[[mock-fail:imagen]]" in failure_cases[0].original_prompt
    assert all("[[mock-fail:imagen]]" not in case.original_prompt for case in default_cases)


def test_runner_generates_matched_pairs_downloads_assets_and_cleans_backend(
    tmp_path: Path,
):
    cases = _benchmark_cases(2)
    config = _config(tmp_path, cases)
    client = FakeEvaluationClient()

    manifest = run_pairs(config, client=client, now=IncrementingClock())

    assert manifest.lifecycle == RunLifecycle.SCORING
    assert [payload["prompt"] for payload in client.created_payloads] == [
        "prompt 0",
        "prompt 0 [mock enhanced]",
        "prompt 1 [mock enhanced]",
        "prompt 1",
    ]
    assert all(payload["model"] == cases[0].target_model for payload in client.created_payloads)
    assert all(payload["aspect_ratio"] == "1:1" for payload in client.created_payloads)
    assert all(payload["number_of_images"] == 1 for payload in client.created_payloads)
    assert client.created_payloads[0].get("enhancement_id") is None
    assert client.created_payloads[1]["enhancement_id"] == "enhancement-1"
    assert client.created_payloads[2]["enhancement_id"] == "enhancement-2"
    assert client.created_payloads[3].get("enhancement_id") is None
    assert client.deleted_job_ids == ["job-1", "job-2", "job-3", "job-4"]

    run_dir = config.runs_dir / config.run_id
    pairs_path = run_dir / "pairs.jsonl"
    assert manifest.artifact_hashes["pairs.jsonl"] == file_sha256(pairs_path)
    cleanup = load_cleanup_record(run_dir / "cleanup.json")
    assert cleanup.policy == CleanupPolicy.DELETE_BACKEND
    assert len(cleanup.jobs) == 4
    assert all(job.state == BackendArtifactState.DELETED for job in cleanup.jobs)
    assert manifest.artifact_hashes["cleanup.json"] == file_sha256(
        run_dir / "cleanup.json"
    )
    for pair in manifest.pairs:
        assert pair.raw.status == ArmStatus.COMPLETED
        assert pair.enhanced.status == ArmStatus.COMPLETED
        for arm in (pair.raw, pair.enhanced):
            assert arm.assets
            asset_path = run_dir / arm.assets[0].relative_path
            assert asset_path.exists()
            assert file_sha256(asset_path) == arm.assets[0].sha256


def test_keep_artifacts_preserves_backend_jobs(tmp_path: Path):
    config = _config(tmp_path, _benchmark_cases(1), keep_artifacts=True)
    client = FakeEvaluationClient()

    manifest = run_pairs(config, client=client, now=IncrementingClock())

    assert client.deleted_job_ids == []
    cleanup = load_cleanup_record(config.runs_dir / config.run_id / "cleanup.json")
    assert cleanup.policy == CleanupPolicy.KEEP_BACKEND
    assert len(cleanup.jobs) == 2
    assert all(job.state == BackendArtifactState.RETAINED for job in cleanup.jobs)


def test_resume_reuses_completed_arms_without_new_enhancement_or_generation(
    tmp_path: Path,
):
    config = _config(tmp_path, _benchmark_cases(1), keep_artifacts=True)
    client = FakeEvaluationClient()
    run_pairs(config, client=client, now=IncrementingClock())
    generation_count = len(client.created_payloads)
    enhancement_count = len(client.enhancement_payloads)

    resumed = run_pairs(config, client=client, now=IncrementingClock())

    assert resumed.lifecycle == RunLifecycle.SCORING
    assert len(client.created_payloads) == generation_count
    assert len(client.enhancement_payloads) == enhancement_count


def test_resume_polls_submitted_job_without_duplicate_generation(tmp_path: Path):
    config = _config(tmp_path, _benchmark_cases(1), keep_artifacts=True)
    client = FakeEvaluationClient(interrupt_next_poll=True)

    with pytest.raises(EvaluationRunnerError, match="simulated connection interruption"):
        run_pairs(config, client=client, now=IncrementingClock())

    interrupted = load_run_manifest(config.runs_dir / config.run_id / "manifest.json")
    assert interrupted.pairs[0].raw.status == ArmStatus.SUBMITTED
    assert len(client.created_payloads) == 1

    resumed = run_pairs(config, client=client, now=IncrementingClock())

    assert resumed.lifecycle == RunLifecycle.SCORING
    assert len(client.created_payloads) == 2
    assert [payload["prompt"] for payload in client.created_payloads].count("prompt 0") == 1


def test_terminal_failure_is_checkpointed_and_backend_job_is_cleaned(tmp_path: Path):
    cases = _benchmark_cases(1, failing=True)
    config = _config(tmp_path, cases)
    client = FakeEvaluationClient(fail_prompt_fragment="[[mock-fail:imagen]]")

    with pytest.raises(GenerationFailedError, match="mock_generation_failed"):
        run_pairs(config, client=client, now=IncrementingClock())

    manifest = load_run_manifest(config.runs_dir / config.run_id / "manifest.json")
    assert manifest.lifecycle == RunLifecycle.FAILED
    assert manifest.last_error is not None
    assert manifest.last_error.code == "mock_generation_failed"
    assert manifest.pairs[0].raw.status == ArmStatus.FAILED
    assert manifest.pairs[0].raw.retry_count == 1
    cleanup = load_cleanup_record(config.runs_dir / config.run_id / "cleanup.json")
    assert cleanup.policy == CleanupPolicy.DELETE_BACKEND
    assert cleanup.jobs[0].state == BackendArtifactState.DELETED
    assert client.deleted_job_ids == ["job-1"]


def test_non_mock_health_is_rejected_before_any_generation(tmp_path: Path):
    config = _config(tmp_path, _benchmark_cases(1))
    client = FakeEvaluationClient(provider_status="ready")

    with pytest.raises(EvaluationRunnerError, match="mock_provider"):
        run_pairs(config, client=client, now=IncrementingClock())

    assert client.enhancement_payloads == []
    assert client.created_payloads == []
    assert not (config.runs_dir / config.run_id).exists()


def test_vertex_runner_records_real_provenance_with_ready_health(tmp_path: Path):
    config = _config(tmp_path, _benchmark_cases(1), keep_artifacts=True)
    adapters = tuple(
        MetricAdapterConfig(
            metric=metric,
            adapter=f"offline_{metric.value}_test",
            model_revision=f"{metric.value}-revision",
            evidence_kind=EvidenceKind.REAL,
            settings={},
        )
        for metric in MetricName
    )
    statistics = StatisticsConfig(
        bootstrap_seed=6600,
        bootstrap_resamples=10000,
        tie_thresholds={
            MetricName.VQA_SCORE: 0.001,
            MetricName.IMAGE_REWARD: 0.01,
            MetricName.TIFA: 0.0,
        },
    )
    config = replace(
        config,
        provider_mode=ProviderMode.VERTEX,
        evidence_kind=EvidenceKind.REAL,
        metric_adapters=adapters,
        statistics=statistics,
        expected_provider_retry_max_attempts=3,
    )
    mismatched = FakeEvaluationClient(
        provider_status="ready",
        provider_retry_max_attempts=4,
    )
    with pytest.raises(EvaluationRunnerError, match="retry cap"):
        run_pairs(
            config,
            client=mismatched,
            environ={"AI_PROVIDER": "vertex"},
            now=IncrementingClock(),
        )
    assert mismatched.enhancement_payloads == []

    client = FakeEvaluationClient(provider_status="ready")

    manifest = run_pairs(
        config,
        client=client,
        environ={"AI_PROVIDER": "vertex"},
        now=IncrementingClock(),
    )

    assert manifest.provider_mode == ProviderMode.VERTEX
    assert manifest.evidence_kind == EvidenceKind.REAL
    assert manifest.metric_adapters == adapters
    assert manifest.statistics == statistics


def test_process_environment_requires_mock_without_echoing_value():
    require_mock_provider({"AI_PROVIDER": "mock"})
    unsafe_value = "vertex-secret-provider-value"

    with pytest.raises(EvaluationRunnerError) as exc_info:
        require_mock_provider({"AI_PROVIDER": unsafe_value})

    assert unsafe_value not in str(exc_info.value)
    assert "AI_PROVIDER=mock" in str(exc_info.value)


def test_runner_does_not_import_production_or_vertex_modules():
    source = Path(generate_pairs.__file__).read_text(encoding="utf-8")

    assert "from app" not in source
    assert "import app" not in source
    assert "google.genai" not in source
    assert "get_vertex_client" not in source


def test_env_file_validation_rejects_dotenv_and_requires_mock(tmp_path: Path):
    sensitive = tmp_path / ".env"
    sensitive.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    with pytest.raises(EvaluationRunnerError, match=r"Refusing.*\.env"):
        validate_mock_env_file(sensitive)

    unsafe = tmp_path / "vertex.env.example"
    unsafe.write_text("AI_PROVIDER=vertex\n", encoding="utf-8")
    with pytest.raises(EvaluationRunnerError, match="AI_PROVIDER=mock"):
        validate_mock_env_file(unsafe)

    safe = tmp_path / "mock.env.example"
    safe.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    validate_mock_env_file(safe)
