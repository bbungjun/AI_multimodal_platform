from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from generate_pairs import (
    DEFAULT_BENCHMARK,
    DEFAULT_RUNS_DIR,
    IDENTIFIER_RE,
    PACKAGE_ROOT,
    REPO_ROOT,
    EvaluationClient,
    EvaluationRunnerError,
    GenerationFailedError,
    HttpClient,
    RunnerConfig,
    require_mock_provider,
    run_pairs,
    start_compose,
    validate_mock_env_file,
)
from schemas import (
    AggregateReport,
    ArmStatus,
    BackendArtifactState,
    CleanupPolicy,
    EvidenceKind,
    MetricName,
    ProviderMode,
    RunLifecycle,
    RunManifest,
    file_sha256,
    load_benchmark_cases,
    load_case_metric_records,
    load_cleanup_record,
    load_run_manifest,
    load_score_records,
    load_summary,
)
from score_pairs import ScoringError, score_run
from summarize import SummaryError, summarize_run


DEFAULT_FAILURE_BENCHMARK = PACKAGE_ROOT / "fixtures" / "benchmark.failure.v1.jsonl"
DEFAULT_MODEL_CACHE_DIR = PACKAGE_ROOT / ".model-cache"
CONTROLLED_FAILURE_SENTINEL = "[[mock-fail:imagen]]"
REQUIRED_SUCCESS_ARTIFACTS = (
    "benchmark.jsonl",
    "cleanup.json",
    "pairs.jsonl",
    "scores.jsonl",
    "case_statistics.jsonl",
    "summary.json",
    "report.md",
)


class MockE2EError(RuntimeError):
    """Raised when the complete mock evaluation gate is not satisfied."""


@dataclass(frozen=True)
class MockE2EConfig:
    base_url: str
    benchmark_path: Path
    failure_benchmark_path: Path
    runs_dir: Path
    model_cache_dir: Path
    run_id: str
    keep_artifacts: bool
    poll_timeout_sec: float
    poll_interval_sec: float
    health_timeout_sec: float
    expected_enhancer_model: str
    expected_template_version: str
    git_sha: str
    dirty_worktree: bool
    expected_failure_code: str = "mock_provider_failure"
    repo_root: Path = REPO_ROOT

    def __post_init__(self) -> None:
        for label, value in (
            ("run_id", self.run_id),
            ("failure_run_id", self.failure_run_id),
            ("expected_failure_code", self.expected_failure_code),
        ):
            if not IDENTIFIER_RE.fullmatch(value):
                raise MockE2EError(f"{label} is not a valid artifact identifier")

    @property
    def failure_run_id(self) -> str:
        return f"{self.run_id}-failure"


@dataclass(frozen=True)
class MockE2EResult:
    manifest: RunManifest
    report: AggregateReport
    failure_manifest: RunManifest


def run_mock_e2e(
    config: MockE2EConfig,
    *,
    environ: Mapping[str, str],
    client: EvaluationClient | None = None,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    announce: Callable[[str], None] | None = None,
) -> MockE2EResult:
    require_mock_provider(environ)
    _validate_controlled_failure_fixture(config.failure_benchmark_path)
    verify_artifact_hygiene(
        repo_root=config.repo_root,
        runs_dir=config.runs_dir,
        model_cache_dir=config.model_cache_dir,
    )

    clock = now or _utc_now
    evaluation_client = client or HttpClient(config.base_url)
    emit = announce or (lambda _: None)

    emit("success flow")
    manifest, report = _run_success_flow(
        config,
        environ=environ,
        client=evaluation_client,
        now=clock,
        monotonic=monotonic,
        sleep=sleep,
    )
    first_identity = _run_identity(manifest)

    emit("resume verification")
    resumed_manifest, resumed_report = _run_success_flow(
        config,
        environ=environ,
        client=evaluation_client,
        now=clock,
        monotonic=monotonic,
        sleep=sleep,
    )
    if _run_identity(resumed_manifest) != first_identity:
        raise MockE2EError(
            "Resume changed completed job ids, asset hashes, or artifact hashes"
        )
    if resumed_report != report:
        raise MockE2EError("Resume changed the completed aggregate report")

    emit("controlled failure")
    failure_manifest = _run_controlled_failure(
        config,
        environ=environ,
        client=evaluation_client,
        now=clock,
        monotonic=monotonic,
        sleep=sleep,
    )

    verify_artifact_hygiene(
        repo_root=config.repo_root,
        runs_dir=config.runs_dir,
        model_cache_dir=config.model_cache_dir,
    )
    return MockE2EResult(
        manifest=resumed_manifest,
        report=resumed_report,
        failure_manifest=failure_manifest,
    )


def _run_success_flow(
    config: MockE2EConfig,
    *,
    environ: Mapping[str, str],
    client: EvaluationClient,
    now: Callable[[], datetime],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> tuple[RunManifest, AggregateReport]:
    runner_config = _runner_config(
        config,
        benchmark_path=config.benchmark_path,
        run_id=config.run_id,
    )
    run_pairs(
        runner_config,
        client=client,
        environ=environ,
        now=now,
        monotonic=monotonic,
        sleep=sleep,
    )
    run_dir = config.runs_dir / config.run_id
    score_run(run_dir, environ=environ, now=now)
    summarize_run(run_dir, environ=environ, now=now)
    return _verify_success_run(run_dir, config)


def _run_controlled_failure(
    config: MockE2EConfig,
    *,
    environ: Mapping[str, str],
    client: EvaluationClient,
    now: Callable[[], datetime],
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> RunManifest:
    run_dir = config.runs_dir / config.failure_run_id
    manifest_path = run_dir / "manifest.json"
    if manifest_path.is_file():
        existing = load_run_manifest(manifest_path)
        if existing.lifecycle == RunLifecycle.FAILED:
            return _verify_failure_run(run_dir, config, existing)

    runner_config = _runner_config(
        config,
        benchmark_path=config.failure_benchmark_path,
        run_id=config.failure_run_id,
    )
    try:
        run_pairs(
            runner_config,
            client=client,
            environ=environ,
            now=now,
            monotonic=monotonic,
            sleep=sleep,
        )
    except GenerationFailedError:
        failed = load_run_manifest(manifest_path)
        return _verify_failure_run(run_dir, config, failed)
    raise MockE2EError(
        "Controlled failure benchmark unexpectedly completed generation"
    )


def _runner_config(
    config: MockE2EConfig,
    *,
    benchmark_path: Path,
    run_id: str,
) -> RunnerConfig:
    return RunnerConfig(
        base_url=config.base_url,
        benchmark_path=benchmark_path,
        runs_dir=config.runs_dir,
        run_id=run_id,
        keep_artifacts=config.keep_artifacts,
        poll_timeout_sec=config.poll_timeout_sec,
        poll_interval_sec=config.poll_interval_sec,
        expected_enhancer_model=config.expected_enhancer_model,
        expected_template_version=config.expected_template_version,
        git_sha=config.git_sha,
        dirty_worktree=config.dirty_worktree,
        health_timeout_sec=config.health_timeout_sec,
    )


def _verify_success_run(
    run_dir: Path,
    config: MockE2EConfig,
) -> tuple[RunManifest, AggregateReport]:
    manifest = load_run_manifest(run_dir / "manifest.json")
    if manifest.lifecycle != RunLifecycle.COMPLETED:
        raise MockE2EError(
            f"Success manifest must be completed, got {manifest.lifecycle.value}"
        )
    if (
        manifest.provider_mode != ProviderMode.MOCK
        or manifest.evidence_kind != EvidenceKind.SYNTHETIC
    ):
        raise MockE2EError("Success manifest must be mock synthetic evidence")
    _verify_manifest_provenance(
        manifest,
        config,
        benchmark_path=config.benchmark_path,
        run_id=config.run_id,
    )

    for name in REQUIRED_SUCCESS_ARTIFACTS:
        _verify_artifact_hash(run_dir, manifest, name)
    if any(
        arm.status != ArmStatus.COMPLETED
        for pair in manifest.pairs
        for arm in (pair.raw, pair.enhanced)
    ):
        raise MockE2EError("Every success case must complete both paired arms")

    scores = load_score_records(run_dir / "scores.jsonl")
    expected_score_count = sum(
        len(arm.assets) * len(MetricName)
        for pair in manifest.pairs
        for arm in (pair.raw, pair.enhanced)
    )
    if len(scores) != expected_score_count:
        raise MockE2EError(
            f"Expected {expected_score_count} image scores, found {len(scores)}"
        )
    if any(score.evidence_kind != EvidenceKind.SYNTHETIC for score in scores):
        raise MockE2EError("Every mock image score must be synthetic")

    case_metrics = load_case_metric_records(run_dir / "case_statistics.jsonl")
    expected_case_metric_count = len(manifest.pairs) * len(MetricName)
    if len(case_metrics) != expected_case_metric_count:
        raise MockE2EError(
            f"Expected {expected_case_metric_count} case metrics, "
            f"found {len(case_metrics)}"
        )

    report = load_summary(run_dir / "summary.json")
    if report.completed_case_count != len(manifest.pairs) or report.missing_cases:
        raise MockE2EError("Success report must include every paired benchmark case")
    if {metric.metric for metric in report.metrics} != set(MetricName):
        raise MockE2EError("Success report must keep all three metrics separate")
    report_text = (run_dir / "report.md").read_text(encoding="utf-8")
    if (
        "SYNTHETIC MOCK EVIDENCE" not in report_text
        or "실제 이미지 품질 근거가 아닙니다" not in report_text
    ):
        raise MockE2EError("Mock report is missing the synthetic evidence warning")

    cleanup = load_cleanup_record(run_dir / "cleanup.json")
    expected_policy = (
        CleanupPolicy.KEEP_BACKEND
        if config.keep_artifacts
        else CleanupPolicy.DELETE_BACKEND
    )
    expected_state = (
        BackendArtifactState.RETAINED
        if config.keep_artifacts
        else BackendArtifactState.DELETED
    )
    expected_jobs = len(manifest.pairs) * 2
    if cleanup.policy != expected_policy or len(cleanup.jobs) != expected_jobs:
        raise MockE2EError("Success cleanup record does not match the run policy")
    if any(job.state != expected_state for job in cleanup.jobs):
        raise MockE2EError("Success cleanup job state does not match the run policy")
    return manifest, report


def _verify_failure_run(
    run_dir: Path,
    config: MockE2EConfig,
    manifest: RunManifest,
) -> RunManifest:
    if manifest.lifecycle != RunLifecycle.FAILED or manifest.last_error is None:
        raise MockE2EError("Controlled failure manifest must preserve a failure")
    if manifest.last_error.code != config.expected_failure_code:
        raise MockE2EError(
            "Controlled failure code mismatch: "
            f"expected {config.expected_failure_code}, got {manifest.last_error.code}"
        )
    _verify_manifest_provenance(
        manifest,
        config,
        benchmark_path=config.failure_benchmark_path,
        run_id=config.failure_run_id,
    )
    for name in ("benchmark.jsonl", "cleanup.json"):
        _verify_artifact_hash(run_dir, manifest, name)
    if not any(
        arm.status == ArmStatus.FAILED
        for pair in manifest.pairs
        for arm in (pair.raw, pair.enhanced)
    ):
        raise MockE2EError("Controlled failure did not preserve a failed arm")

    cleanup = load_cleanup_record(run_dir / "cleanup.json")
    expected_policy = (
        CleanupPolicy.KEEP_BACKEND
        if config.keep_artifacts
        else CleanupPolicy.DELETE_BACKEND
    )
    expected_state = (
        BackendArtifactState.RETAINED
        if config.keep_artifacts
        else BackendArtifactState.DELETED
    )
    if cleanup.policy != expected_policy or not cleanup.jobs:
        raise MockE2EError("Controlled failure cleanup record is incomplete")
    if any(job.state != expected_state for job in cleanup.jobs):
        raise MockE2EError("Controlled failure cleanup state does not match policy")
    for forbidden in ("scores.jsonl", "case_statistics.jsonl", "summary.json", "report.md"):
        if (run_dir / forbidden).exists():
            raise MockE2EError(
                f"Controlled failure must not create downstream artifact {forbidden}"
            )
    return manifest


def _verify_manifest_provenance(
    manifest: RunManifest,
    config: MockE2EConfig,
    *,
    benchmark_path: Path,
    run_id: str,
) -> None:
    problems: list[str] = []
    if manifest.run_id != run_id:
        problems.append("run_id")
    if manifest.provider_mode != ProviderMode.MOCK:
        problems.append("provider_mode")
    if manifest.evidence_kind != EvidenceKind.SYNTHETIC:
        problems.append("evidence_kind")
    if manifest.benchmark_sha256 != file_sha256(benchmark_path):
        problems.append("benchmark_sha256")
    if manifest.git_sha != config.git_sha:
        problems.append("git_sha")
    if manifest.dirty_worktree != config.dirty_worktree:
        problems.append("dirty_worktree")
    if manifest.enhancer.model != config.expected_enhancer_model:
        problems.append("enhancer.model")
    if manifest.enhancer.template_version != config.expected_template_version:
        problems.append("enhancer.template_version")
    if problems:
        raise MockE2EError(
            "Run provenance does not match this smoke invocation: "
            + ", ".join(problems)
        )


def _verify_artifact_hash(
    run_dir: Path,
    manifest: RunManifest,
    name: str,
) -> None:
    path = run_dir / name
    expected = manifest.artifact_hashes.get(name)
    if expected is None or not path.is_file() or file_sha256(path) != expected:
        raise MockE2EError(f"Artifact {name} is missing or does not match manifest hash")


def _validate_controlled_failure_fixture(path: Path) -> None:
    cases = [case for case in load_benchmark_cases(path) if case.enabled]
    if not cases:
        raise MockE2EError("Controlled failure benchmark has no enabled case")
    if any(CONTROLLED_FAILURE_SENTINEL not in case.original_prompt for case in cases):
        raise MockE2EError(
            "Every controlled failure case must contain the explicit mock failure sentinel"
        )


def _run_identity(manifest: RunManifest) -> tuple[object, ...]:
    pair_identity = tuple(
        (
            pair.case_id,
            pair.raw.job_id,
            tuple(asset.sha256 for asset in pair.raw.assets),
            pair.enhanced.job_id,
            tuple(asset.sha256 for asset in pair.enhanced.assets),
        )
        for pair in manifest.pairs
    )
    return pair_identity, tuple(sorted(manifest.artifact_hashes.items()))


def verify_artifact_hygiene(
    *,
    repo_root: Path,
    runs_dir: Path,
    model_cache_dir: Path,
) -> None:
    root = repo_root.resolve()
    for label, directory in (
        ("evaluation runs", runs_dir),
        ("evaluator model cache", model_cache_dir),
    ):
        resolved = directory.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        probe = (relative / ".mock-gate-ignore-probe").as_posix()
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", probe],
            cwd=root,
            check=False,
        )
        if ignored.returncode != 0:
            raise MockE2EError(
                f"{label} path is inside the repository but is not gitignored: {relative}"
            )
        status = subprocess.run(
            [
                "git",
                "status",
                "--short",
                "--untracked-files=all",
                "--",
                relative.as_posix(),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if status.returncode != 0:
            raise MockE2EError(f"Unable to verify git hygiene for {label}")
        if status.stdout.strip():
            raise MockE2EError(f"{label} contains staged or visible worktree files")


def _git_metadata() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if sha.returncode != 0 or not sha.stdout.strip():
        raise MockE2EError("Unable to determine Git SHA for mock gate")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        raise MockE2EError("Unable to determine Git worktree state for mock gate")
    return sha.stdout.strip(), bool(status.stdout.strip())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("mock-gate-%Y%m%dT%H%M%SZ")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run generation, synthetic scoring, paired statistics, resume, and "
            "controlled failure as one mock-only evaluation gate."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument(
        "--failure-benchmark",
        type=Path,
        default=DEFAULT_FAILURE_BENCHMARK,
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--model-cache-dir", type=Path, default=DEFAULT_MODEL_CACHE_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--poll-timeout-sec", type=float, default=60.0)
    parser.add_argument("--poll-interval-sec", type=float, default=1.0)
    parser.add_argument("--health-timeout-sec", type=float, default=60.0)
    parser.add_argument("--enhancer-model", default="gemini-2.5-flash")
    parser.add_argument("--template-version", default="v1")
    parser.add_argument("--compose", action="store_true")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env.example")
    parser.add_argument("--keep-artifacts", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        require_mock_provider(os.environ)
        validate_mock_env_file(args.env_file)
        if args.compose:
            start_compose(args.env_file)
        git_sha, dirty_worktree = _git_metadata()
        config = MockE2EConfig(
            base_url=args.base_url,
            benchmark_path=args.benchmark,
            failure_benchmark_path=args.failure_benchmark,
            runs_dir=args.runs_dir,
            model_cache_dir=args.model_cache_dir,
            run_id=args.run_id or _default_run_id(),
            keep_artifacts=args.keep_artifacts,
            poll_timeout_sec=args.poll_timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            health_timeout_sec=args.health_timeout_sec,
            expected_enhancer_model=args.enhancer_model,
            expected_template_version=args.template_version,
            git_sha=git_sha,
            dirty_worktree=dirty_worktree,
        )
        result = run_mock_e2e(
            config,
            environ=os.environ,
            announce=lambda step: print(f"[mock-eval-gate] {step}", flush=True),
        )
    except KeyboardInterrupt:
        print(
            "MOCK EVALUATION GATE INTERRUPTED: checkpoints are preserved for resume",
            file=sys.stderr,
        )
        return 130
    except (
        EvaluationRunnerError,
        MockE2EError,
        OSError,
        ScoringError,
        SummaryError,
        ValueError,
    ) as exc:
        print(f"MOCK EVALUATION GATE FAILED: {exc}", file=sys.stderr)
        return 1

    print(
        "MOCK EVALUATION GATE PASSED — SYNTHETIC EVIDENCE ONLY. "
        f"run_id={result.manifest.run_id} "
        f"cases={result.report.completed_case_count} "
        f"failure_code={result.failure_manifest.last_error.code}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
