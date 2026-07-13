from __future__ import annotations

from pathlib import Path

import pytest

import run_mock_e2e
from generate_pairs import EvaluationRunnerError
from run_mock_e2e import (
    DEFAULT_MODEL_CACHE_DIR,
    MockE2EConfig,
    MockE2EError,
    run_mock_e2e as execute_mock_gate,
    verify_artifact_hygiene,
)
from schemas import (
    ArmStatus,
    RunLifecycle,
    file_sha256,
    load_case_metric_records,
    load_run_manifest,
    load_score_records,
    write_benchmark_cases,
)
from tests.test_generate_pairs import (
    FakeEvaluationClient,
    IncrementingClock,
    _benchmark_cases,
)


EVAL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_ROOT.parents[1]


def _config(tmp_path: Path, *, case_count: int = 2) -> MockE2EConfig:
    benchmark_path = tmp_path / "benchmark.v1.jsonl"
    failure_benchmark_path = tmp_path / "benchmark.failure.v1.jsonl"
    write_benchmark_cases(benchmark_path, _benchmark_cases(case_count))
    write_benchmark_cases(
        failure_benchmark_path,
        _benchmark_cases(1, failing=True),
    )
    return MockE2EConfig(
        base_url="http://fake.test",
        benchmark_path=benchmark_path,
        failure_benchmark_path=failure_benchmark_path,
        runs_dir=tmp_path / "runs",
        model_cache_dir=tmp_path / ".model-cache",
        run_id="mock-e2e-gate-001",
        keep_artifacts=False,
        poll_timeout_sec=1,
        poll_interval_sec=0,
        health_timeout_sec=1,
        expected_enhancer_model="gemini-2.5-flash",
        expected_template_version="v1",
        git_sha="4a44ec0",
        dirty_worktree=False,
        expected_failure_code="mock_generation_failed",
        repo_root=REPO_ROOT,
    )


def _mock_environment() -> dict[str, str]:
    return {
        "AI_PROVIDER": "mock",
        "GOOGLE_APPLICATION_CREDENTIALS": "missing-credential-must-not-be-read.json",
        "VERTEX_PROJECT_ID": "must-not-be-used",
    }


def test_complete_mock_gate_runs_success_resume_and_controlled_failure(
    tmp_path: Path,
):
    config = _config(tmp_path)
    client = FakeEvaluationClient(
        fail_prompt_fragment="[[mock-fail:imagen]]"
    )
    clock = IncrementingClock()
    phases: list[str] = []

    result = execute_mock_gate(
        config,
        environ=_mock_environment(),
        client=client,
        now=clock,
        announce=phases.append,
    )

    assert phases == ["success flow", "resume verification", "controlled failure"]
    assert result.manifest.lifecycle == RunLifecycle.COMPLETED
    assert result.report.completed_case_count == 2
    assert result.failure_manifest.lifecycle == RunLifecycle.FAILED
    assert result.failure_manifest.last_error is not None
    assert result.failure_manifest.last_error.code == "mock_generation_failed"
    assert len(client.created_payloads) == 5
    assert len(client.enhancement_payloads) == 3
    assert len(client.deleted_job_ids) == 5

    run_dir = config.runs_dir / config.run_id
    assert len(load_score_records(run_dir / "scores.jsonl")) == 12
    assert len(load_case_metric_records(run_dir / "case_statistics.jsonl")) == 6
    first_hashes = {
        name: file_sha256(run_dir / name)
        for name in (
            "scores.jsonl",
            "case_statistics.jsonl",
            "summary.json",
            "report.md",
        )
    }
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "SYNTHETIC MOCK EVIDENCE" in report_text
    assert "실제 이미지 품질 근거가 아닙니다" in report_text

    repeated = execute_mock_gate(
        config,
        environ=_mock_environment(),
        client=client,
        now=clock,
    )

    assert repeated == result
    assert len(client.created_payloads) == 5
    assert len(client.enhancement_payloads) == 3
    assert len(client.deleted_job_ids) == 5
    assert {
        name: file_sha256(run_dir / name) for name in first_hashes
    } == first_hashes


def test_gate_resumes_submitted_job_after_interruption_without_duplicate_request(
    tmp_path: Path,
):
    config = _config(tmp_path, case_count=1)
    client = FakeEvaluationClient(
        interrupt_next_poll=True,
        fail_prompt_fragment="[[mock-fail:imagen]]",
    )
    clock = IncrementingClock()

    with pytest.raises(EvaluationRunnerError, match="simulated connection interruption"):
        execute_mock_gate(
            config,
            environ=_mock_environment(),
            client=client,
            now=clock,
        )

    interrupted = load_run_manifest(
        config.runs_dir / config.run_id / "manifest.json"
    )
    assert interrupted.pairs[0].raw.status == ArmStatus.SUBMITTED
    assert len(client.created_payloads) == 1

    result = execute_mock_gate(
        config,
        environ=_mock_environment(),
        client=client,
        now=clock,
    )

    assert result.manifest.lifecycle == RunLifecycle.COMPLETED
    assert len(client.created_payloads) == 3
    assert [payload["prompt"] for payload in client.created_payloads].count(
        "prompt 0"
    ) == 1


def test_gate_rejects_non_mock_environment_before_creating_artifacts(tmp_path: Path):
    config = _config(tmp_path)

    with pytest.raises(EvaluationRunnerError, match="AI_PROVIDER=mock"):
        execute_mock_gate(
            config,
            environ={"AI_PROVIDER": "vertex"},
            client=FakeEvaluationClient(),
        )

    assert not config.runs_dir.exists()


def test_gate_requires_explicit_failure_sentinel_before_requests(tmp_path: Path):
    config = _config(tmp_path)
    write_benchmark_cases(
        config.failure_benchmark_path,
        _benchmark_cases(1, failing=False),
    )
    client = FakeEvaluationClient()

    with pytest.raises(MockE2EError, match="mock failure sentinel"):
        execute_mock_gate(
            config,
            environ=_mock_environment(),
            client=client,
        )

    assert client.calls == []
    assert not config.runs_dir.exists()


def test_default_run_and_model_cache_paths_are_gitignored():
    verify_artifact_hygiene(
        repo_root=REPO_ROOT,
        runs_dir=EVAL_ROOT / "runs",
        model_cache_dir=DEFAULT_MODEL_CACHE_DIR,
    )

    with pytest.raises(MockE2EError, match="not gitignored"):
        verify_artifact_hygiene(
            repo_root=REPO_ROOT,
            runs_dir=EVAL_ROOT / "unignored-evaluation-runs",
            model_cache_dir=DEFAULT_MODEL_CACHE_DIR,
        )


def test_main_rejects_dotenv_before_git_or_provider_work(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    sensitive = tmp_path / ".env"
    sensitive.write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    assert run_mock_e2e.main(
        ["--env-file", str(sensitive), "--run-id", "must-not-run"]
    ) == 1

    captured = capsys.readouterr()
    assert "Refusing to read sensitive .env" in captured.err
    assert "must-not-be-read" not in captured.err


def test_gate_module_has_no_vertex_or_remote_scorer_dependencies():
    source = Path(run_mock_e2e.__file__).read_text(encoding="utf-8")

    for forbidden in (
        "from app",
        "import app",
        "google.genai",
        "vertexai",
        "import torch",
        "transformers",
        "requests.",
    ):
        assert forbidden not in source
