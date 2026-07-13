from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from uuid import uuid4

from schemas import (
    BackendArtifactState,
    CURRENT_SCHEMA_VERSION,
    ArmName,
    ArmOrder,
    ArmRecord,
    ArmStatus,
    AssetRecord,
    BenchmarkCase,
    CleanupPolicy,
    CleanupRecord,
    EnhancerConfig,
    EvidenceKind,
    FailureRecord,
    MetricAdapterConfig,
    MetricName,
    JobCleanupRecord,
    PairRecord,
    ProviderMode,
    RunLifecycle,
    RunManifest,
    StatisticsConfig,
    file_sha256,
    load_benchmark_cases,
    load_cleanup_record,
    load_run_manifest,
    prompt_sha256,
    write_cleanup_record,
    write_pair_records,
    write_run_manifest,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_BENCHMARK = PACKAGE_ROOT / "benchmark.v1.jsonl"
DEFAULT_RUNS_DIR = PACKAGE_ROOT / "runs"
TERMINAL_STATES = {"completed", "failed", "cancelled"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class EvaluationRunnerError(RuntimeError):
    """Raised for safe, operator-actionable evaluation runner failures."""


class HttpRequestError(EvaluationRunnerError):
    """Raised when the backend HTTP boundary is unavailable or malformed."""


class GenerationFailedError(EvaluationRunnerError):
    """Raised after a terminal generation failure has been checkpointed."""


class EvaluationClient(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        step_name: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        expected_status: int | set[int],
        step_name: str,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str], int]: ...


@dataclass(frozen=True)
class RunnerConfig:
    base_url: str
    benchmark_path: Path
    runs_dir: Path
    run_id: str
    keep_artifacts: bool
    poll_timeout_sec: float
    poll_interval_sec: float
    expected_enhancer_model: str
    expected_template_version: str
    git_sha: str
    dirty_worktree: bool
    health_timeout_sec: float = 60.0

    def __post_init__(self) -> None:
        if not IDENTIFIER_RE.fullmatch(self.run_id):
            raise EvaluationRunnerError(
                "run_id must start with an alphanumeric character and contain only "
                "letters, numbers, '.', '_', or '-' (maximum 128 characters)."
            )
        if self.poll_timeout_sec <= 0 or self.health_timeout_sec <= 0:
            raise EvaluationRunnerError("timeout values must be positive")
        if self.poll_interval_sec < 0:
            raise EvaluationRunnerError("poll_interval_sec must be non-negative")


class HttpClient:
    def __init__(self, base_url: str, *, timeout_sec: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout_sec = timeout_sec

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
        body, _, _ = self.request_bytes(
            method,
            path,
            expected_status=expected_status,
            step_name=step_name,
            payload=payload,
            headers=headers,
        )
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise HttpRequestError(f"{step_name} returned invalid JSON: {exc}") from exc
        if not isinstance(decoded, dict):
            raise HttpRequestError(f"{step_name} expected a JSON object response")
        return decoded

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
        expected = {expected_status} if isinstance(expected_status, int) else expected_status
        request_headers = dict(headers or {})
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(
            urljoin(self.base_url, path.lstrip("/")),
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                body = response.read()
                status = response.status
                response_headers = dict(response.headers.items())
        except HTTPError as exc:
            body = exc.read()
            if exc.code in expected:
                return body, dict(exc.headers.items()), exc.code
            raise HttpRequestError(
                _http_status_message(step_name, exc.code, expected, body)
            ) from exc
        except (URLError, RemoteDisconnected, ConnectionResetError, TimeoutError) as exc:
            raise HttpRequestError(f"{step_name} request failed: {exc}") from exc
        if status not in expected:
            raise HttpRequestError(_http_status_message(step_name, status, expected, body))
        return body, response_headers, status


def _http_status_message(
    step_name: str,
    actual: int,
    expected: set[int],
    body: bytes,
) -> str:
    snippet = body.decode("utf-8", errors="replace").strip()
    if len(snippet) > 500:
        snippet = snippet[:500] + "..."
    expected_text = "/".join(str(status) for status in sorted(expected))
    detail = f": {snippet}" if snippet else ""
    return f"{step_name} expected HTTP {expected_text}, got {actual}{detail}"


def require_mock_provider(environ: Mapping[str, str]) -> None:
    if environ.get("AI_PROVIDER") != "mock":
        raise EvaluationRunnerError(
            "AI_PROVIDER=mock is required. The current environment value is not printed."
        )


def validate_mock_env_file(path: Path) -> None:
    env_path = path.expanduser()
    if env_path.name == ".env":
        raise EvaluationRunnerError(
            "Refusing to read sensitive .env. Use .env.example or another "
            "non-secret mock-only env file."
        )
    if not env_path.is_file():
        raise EvaluationRunnerError(f"Mock env file was not found: {env_path}")

    provider: str | None = None
    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise EvaluationRunnerError(
                f"Mock env file line {line_number} is not KEY=VALUE syntax"
            )
        key, value = line.split("=", 1)
        if key.strip() == "AI_PROVIDER":
            provider = _strip_quotes(value.strip())
    if provider != "mock":
        raise EvaluationRunnerError("Mock env file must contain AI_PROVIDER=mock")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def arm_orders_for_cases(cases: Sequence[BenchmarkCase]) -> dict[str, ArmOrder]:
    enabled_ids = sorted(case.case_id for case in cases if case.enabled)
    return {
        case_id: (
            ArmOrder.RAW_FIRST if index % 2 == 0 else ArmOrder.ENHANCED_FIRST
        )
        for index, case_id in enumerate(enabled_ids)
    }


def run_pairs(
    config: RunnerConfig,
    *,
    client: EvaluationClient | None = None,
    now: Callable[[], datetime] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> RunManifest:
    require_mock_provider(os.environ)
    runner = PairRunner(
        config,
        client=client or HttpClient(config.base_url),
        now=now or _utc_now,
        monotonic=monotonic,
        sleep=sleep,
    )
    return runner.run()


class PairRunner:
    def __init__(
        self,
        config: RunnerConfig,
        *,
        client: EvaluationClient,
        now: Callable[[], datetime],
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.config = config
        self.client = client
        self.now = now
        self.monotonic = monotonic
        self.sleep = sleep
        self.run_dir = config.runs_dir / config.run_id
        self.manifest_path = self.run_dir / "manifest.json"
        self.cleanup_path = self.run_dir / "cleanup.json"

    def run(self) -> RunManifest:
        self._wait_for_mock_health()
        cases = [case for case in load_benchmark_cases(self.config.benchmark_path) if case.enabled]
        if not cases:
            raise EvaluationRunnerError("Benchmark contains no enabled cases")

        manifest = self._load_or_create_manifest(cases)
        if manifest.lifecycle == RunLifecycle.FAILED:
            raise EvaluationRunnerError(
                "Run manifest is failed and cannot resume automatically; inspect the "
                "recorded failure and start a new run_id after correcting it."
            )
        if manifest.lifecycle == RunLifecycle.COMPLETED:
            for pair in manifest.pairs:
                self._verify_local_assets(pair.raw)
                self._verify_local_assets(pair.enhanced)
            return manifest
        if manifest.lifecycle == RunLifecycle.SUMMARIZING:
            raise EvaluationRunnerError(
                "Run is already in summarizing lifecycle; generation runner will not "
                "modify a downstream-owned manifest."
            )

        case_map = {case.case_id: case for case in cases}
        for case in cases:
            pair = self._pair(manifest, case.case_id)
            if pair.enhanced.execution_prompt is None:
                manifest = self._enhance_case(manifest, pair, case)
                pair = self._pair(manifest, case.case_id)

            arm_names = (
                (ArmName.RAW, ArmName.ENHANCED)
                if pair.arm_order == ArmOrder.RAW_FIRST
                else (ArmName.ENHANCED, ArmName.RAW)
            )
            for arm_name in arm_names:
                pair = self._pair(manifest, case.case_id)
                manifest = self._process_arm(manifest, pair, case_map[case.case_id], arm_name)

        for pair in manifest.pairs:
            if pair.raw.status != ArmStatus.COMPLETED or pair.enhanced.status != ArmStatus.COMPLETED:
                raise EvaluationRunnerError(
                    f"Case {pair.case_id} did not finish both paired arms"
                )

        pairs_path = self.run_dir / "pairs.jsonl"
        write_pair_records(pairs_path, list(manifest.pairs))
        artifact_hashes = dict(manifest.artifact_hashes)
        artifact_hashes["pairs.jsonl"] = file_sha256(pairs_path)
        manifest = self._validated_manifest_copy(
            manifest,
            lifecycle=RunLifecycle.SCORING,
            updated_at=self.now(),
            artifact_hashes=artifact_hashes,
            last_error=None,
        )
        write_run_manifest(self.manifest_path, manifest)
        return manifest

    def _wait_for_mock_health(self) -> None:
        deadline = self.monotonic() + self.config.health_timeout_sec
        last_error = "backend health was not requested"
        while self.monotonic() <= deadline:
            try:
                health = self.client.request_json(
                    "GET",
                    "/api/health",
                    expected_status=200,
                    step_name="Mock health",
                )
            except HttpRequestError as exc:
                last_error = str(exc)
                self.sleep(self.config.poll_interval_sec)
                continue
            vertex = health.get("vertex")
            vertex = vertex if isinstance(vertex, dict) else {}
            if (
                health.get("ok") is not True
                or health.get("ready") is not True
                or health.get("db") != "up"
                or vertex.get("status") != "mock_provider"
                or vertex.get("credentials") != "not_required"
            ):
                raise EvaluationRunnerError(
                    "Backend health must report ready DB state, mock_provider, and "
                    "credentials=not_required before evaluation."
                )
            return
        raise EvaluationRunnerError(f"Timed out waiting for mock backend health: {last_error}")

    def _load_or_create_manifest(self, cases: list[BenchmarkCase]) -> RunManifest:
        benchmark_hash = file_sha256(self.config.benchmark_path)
        if self.manifest_path.exists():
            manifest = load_run_manifest(self.manifest_path)
            self._validate_resume_manifest(manifest, cases, benchmark_hash)
            return self._sync_cleanup_artifact(manifest)

        if self.run_dir.exists() and any(self.run_dir.iterdir()):
            raise EvaluationRunnerError(
                f"Run directory already contains files but has no manifest: {self.run_dir}"
            )
        self.run_dir.mkdir(parents=True, exist_ok=True)
        benchmark_snapshot = self.run_dir / "benchmark.jsonl"
        _atomic_write_bytes(benchmark_snapshot, self.config.benchmark_path.read_bytes())
        cleanup = CleanupRecord(
            schema_version=CURRENT_SCHEMA_VERSION,
            run_id=self.config.run_id,
            policy=self._cleanup_policy(),
            jobs=(),
        )
        write_cleanup_record(self.cleanup_path, cleanup)

        created_at = self.now()
        order_map = arm_orders_for_cases(cases)
        pairs = tuple(
            self._planned_pair(case, order_map[case.case_id]) for case in cases
        )
        manifest = RunManifest(
            schema_version=CURRENT_SCHEMA_VERSION,
            run_id=self.config.run_id,
            lifecycle=RunLifecycle.PLANNED,
            started_at=created_at,
            updated_at=created_at,
            completed_at=None,
            git_sha=self.config.git_sha,
            dirty_worktree=self.config.dirty_worktree,
            provider_mode=ProviderMode.MOCK,
            evidence_kind=EvidenceKind.SYNTHETIC,
            benchmark_path="benchmark.jsonl",
            benchmark_sha256=benchmark_hash,
            enhancer=EnhancerConfig(
                model=self.config.expected_enhancer_model,
                template_version=self.config.expected_template_version,
                template_sha256=prompt_sha256(
                    f"template-version:{self.config.expected_template_version}"
                ),
            ),
            generation_models=tuple(sorted({case.target_model for case in cases})),
            metric_adapters=_mock_metric_adapters(),
            statistics=StatisticsConfig(
                bootstrap_seed=6100,
                bootstrap_resamples=1000,
                tie_thresholds={
                    MetricName.VQA_SCORE: 0.0,
                    MetricName.IMAGE_REWARD: 0.0,
                    MetricName.TIFA: 0.0,
                },
            ),
            order_policy="alternating_by_case",
            pairs=pairs,
            artifact_hashes={
                "benchmark.jsonl": benchmark_hash,
                "cleanup.json": file_sha256(self.cleanup_path),
            },
            last_error=None,
        )
        write_run_manifest(self.manifest_path, manifest)
        return manifest

    def _planned_pair(self, case: BenchmarkCase, arm_order: ArmOrder) -> PairRecord:
        raw_order, enhanced_order = (
            (0, 1) if arm_order == ArmOrder.RAW_FIRST else (1, 0)
        )
        requested_parameters = {
            "aspect_ratio": case.aspect_ratio,
            "number_of_images": case.samples_per_arm,
        }
        raw = ArmRecord(
            arm=ArmName.RAW,
            status=ArmStatus.PLANNED,
            request_order=raw_order,
            execution_prompt=case.original_prompt,
            execution_prompt_sha256=prompt_sha256(case.original_prompt),
            enhancement_id=None,
            job_id=None,
            target_model=case.target_model,
            aspect_ratio=case.aspect_ratio,
            requested_samples=case.samples_per_arm,
            generation_parameters=requested_parameters,
            retry_count=0,
            assets=(),
            failure=None,
        )
        enhanced = ArmRecord(
            arm=ArmName.ENHANCED,
            status=ArmStatus.PLANNED,
            request_order=enhanced_order,
            execution_prompt=None,
            execution_prompt_sha256=None,
            enhancement_id=None,
            job_id=None,
            target_model=case.target_model,
            aspect_ratio=case.aspect_ratio,
            requested_samples=case.samples_per_arm,
            generation_parameters=requested_parameters,
            retry_count=0,
            assets=(),
            failure=None,
        )
        evaluation_prompt = case.evaluation_prompt_en or case.evaluation_prompt
        return PairRecord(
            schema_version=CURRENT_SCHEMA_VERSION,
            run_id=self.config.run_id,
            case_id=case.case_id,
            language=case.language,
            category=case.category,
            evaluation_prompt_sha256=prompt_sha256(evaluation_prompt),
            arm_order=arm_order,
            raw=raw,
            enhanced=enhanced,
        )

    def _validate_resume_manifest(
        self,
        manifest: RunManifest,
        cases: list[BenchmarkCase],
        benchmark_hash: str,
    ) -> None:
        problems: list[str] = []
        if manifest.run_id != self.config.run_id:
            problems.append("run_id")
        if manifest.provider_mode != ProviderMode.MOCK:
            problems.append("provider_mode")
        if manifest.evidence_kind != EvidenceKind.SYNTHETIC:
            problems.append("evidence_kind")
        if manifest.benchmark_sha256 != benchmark_hash:
            problems.append("benchmark_sha256")
        if manifest.git_sha != self.config.git_sha:
            problems.append("git_sha")
        if manifest.dirty_worktree != self.config.dirty_worktree:
            problems.append("dirty_worktree")
        if manifest.enhancer.model != self.config.expected_enhancer_model:
            problems.append("enhancer.model")
        if manifest.enhancer.template_version != self.config.expected_template_version:
            problems.append("enhancer.template_version")

        expected_ids = [case.case_id for case in cases]
        if [pair.case_id for pair in manifest.pairs] != expected_ids:
            problems.append("case checkpoints")
        expected_orders = arm_orders_for_cases(cases)
        for case, pair in zip(cases, manifest.pairs, strict=False):
            if pair.arm_order != expected_orders[case.case_id]:
                problems.append(f"{case.case_id}.arm_order")
            if pair.raw.execution_prompt != case.original_prompt:
                problems.append(f"{case.case_id}.raw.prompt")
            for arm in (pair.raw, pair.enhanced):
                if (
                    arm.target_model != case.target_model
                    or arm.aspect_ratio != case.aspect_ratio
                    or arm.requested_samples != case.samples_per_arm
                ):
                    problems.append(f"{case.case_id}.{arm.arm.value}.parameters")

        snapshot = self.run_dir / manifest.benchmark_path
        if not snapshot.is_file() or file_sha256(snapshot) != benchmark_hash:
            problems.append("benchmark snapshot")
        if problems:
            raise EvaluationRunnerError(
                "Run manifest is incompatible with the requested resume: "
                + ", ".join(problems)
            )

    def _enhance_case(
        self,
        manifest: RunManifest,
        pair: PairRecord,
        case: BenchmarkCase,
    ) -> RunManifest:
        manifest = self._checkpoint_pair(
            manifest,
            pair,
            lifecycle=RunLifecycle.ENHANCING,
        )
        response = self.client.request_json(
            "POST",
            "/api/prompts/enhance",
            expected_status=201,
            step_name=f"Enhance {case.case_id}",
            payload={
                "prompt": case.original_prompt,
                "target_mode": "t2i",
                "target_model": case.target_model,
                "creativity_preset": case.creativity_preset.value,
            },
        )
        enhancement_id = _required_identifier(response, "id", "prompt enhancement")
        enhanced_prompt = _required_text(response, "enhanced", "prompt enhancement")
        components = response.get("components")
        if not isinstance(components, dict) or components.get("provider") != "mock":
            raise EvaluationRunnerError(
                f"Enhancement {case.case_id} did not report components.provider=mock"
            )
        expected_fields = {
            "original": case.original_prompt,
            "target_mode": "t2i",
            "target_model": case.target_model,
            "llm_model": self.config.expected_enhancer_model,
            "template_version": self.config.expected_template_version,
            "creativity_preset": case.creativity_preset.value,
        }
        mismatches = [
            field for field, expected in expected_fields.items() if response.get(field) != expected
        ]
        if mismatches:
            raise EvaluationRunnerError(
                f"Enhancement {case.case_id} response mismatched: {', '.join(mismatches)}"
            )

        enhanced = pair.enhanced.model_copy(
            update={
                "execution_prompt": enhanced_prompt,
                "execution_prompt_sha256": prompt_sha256(enhanced_prompt),
                "enhancement_id": enhancement_id,
            }
        )
        updated_pair = self._replace_arm(pair, enhanced)
        return self._checkpoint_pair(
            manifest,
            updated_pair,
            lifecycle=RunLifecycle.ENHANCING,
        )

    def _process_arm(
        self,
        manifest: RunManifest,
        pair: PairRecord,
        case: BenchmarkCase,
        arm_name: ArmName,
    ) -> RunManifest:
        arm = pair.raw if arm_name == ArmName.RAW else pair.enhanced
        if arm.status == ArmStatus.FAILED:
            raise EvaluationRunnerError(
                f"Case {case.case_id} arm {arm_name.value} is already failed"
            )
        if arm.status == ArmStatus.COMPLETED:
            self._verify_local_assets(arm)
            return self._apply_cleanup_policy(manifest, pair, arm)

        lifecycle = (
            RunLifecycle.GENERATING_RAW
            if arm_name == ArmName.RAW
            else RunLifecycle.GENERATING_ENHANCED
        )
        if arm.status == ArmStatus.PLANNED:
            manifest = self._checkpoint_pair(manifest, pair, lifecycle=lifecycle)
            payload: dict[str, Any] = {
                "prompt": arm.execution_prompt,
                "mode": "t2i",
                "model": arm.target_model,
                "aspect_ratio": arm.aspect_ratio,
                "number_of_images": arm.requested_samples,
                "auto_enhance": False,
            }
            if arm_name == ArmName.ENHANCED:
                payload["enhancement_id"] = arm.enhancement_id
            response = self.client.request_json(
                "POST",
                "/api/generations",
                expected_status=201,
                step_name=f"Create {case.case_id} {arm_name.value}",
                payload=payload,
            )
            job_id = _required_identifier(response, "id", "generation")
            parameters = response.get("parameters")
            checkpoint_parameters = (
                dict(parameters)
                if isinstance(parameters, dict)
                else dict(arm.generation_parameters)
            )
            submitted = arm.model_copy(
                update={
                    "status": ArmStatus.SUBMITTED,
                    "job_id": job_id,
                    "generation_parameters": checkpoint_parameters,
                    "retry_count": _retry_count(response),
                }
            )
            pair = self._replace_arm(pair, submitted)
            manifest = self._checkpoint_pair(manifest, pair, lifecycle=lifecycle)
            manifest = self._set_cleanup_state(
                manifest,
                pair,
                submitted,
                BackendArtifactState.RETAINED,
            )
            arm = submitted
            self._validate_job_contract(response, arm)

        if not arm.job_id:
            raise EvaluationRunnerError(
                f"Submitted {case.case_id} {arm_name.value} arm has no job_id"
            )
        job = self._poll_job(arm)
        state = job.get("state")
        if state in {"failed", "cancelled"}:
            return self._record_terminal_failure(manifest, pair, arm, job)
        if state != "completed":
            raise EvaluationRunnerError(
                f"Job {arm.job_id} returned unexpected terminal state {state!r}"
            )

        manifest = self._checkpoint_pair(
            manifest,
            pair,
            lifecycle=RunLifecycle.COLLECTING_ASSETS,
        )
        completed = self._collect_assets(case.case_id, arm, job)
        pair = self._replace_arm(pair, completed)
        manifest = self._checkpoint_pair(
            manifest,
            pair,
            lifecycle=RunLifecycle.COLLECTING_ASSETS,
        )
        return self._apply_cleanup_policy(manifest, pair, completed)

    def _poll_job(self, arm: ArmRecord) -> dict[str, Any]:
        assert arm.job_id is not None
        deadline = self.monotonic() + self.config.poll_timeout_sec
        last_state: object = None
        while self.monotonic() <= deadline:
            job = self.client.request_json(
                "GET",
                f"/api/generations/{arm.job_id}",
                expected_status=200,
                step_name=f"Poll {arm.job_id}",
            )
            self._validate_job_contract(job, arm)
            last_state = job.get("state")
            if last_state in TERMINAL_STATES:
                return job
            self.sleep(self.config.poll_interval_sec)
        raise EvaluationRunnerError(
            f"Timed out polling job {arm.job_id}; last state was {last_state!r}. "
            "The submitted checkpoint is preserved for resume."
        )

    def _validate_job_contract(self, job: dict[str, Any], arm: ArmRecord) -> None:
        expected = {
            "id": arm.job_id,
            "mode": "t2i",
            "model": arm.target_model,
            "prompt": arm.execution_prompt,
            "execution_prompt_sha256": arm.execution_prompt_sha256,
            "enhancement_id": (
                arm.enhancement_id if arm.arm == ArmName.ENHANCED else None
            ),
        }
        mismatches = [
            field for field, value in expected.items() if job.get(field) != value
        ]
        parameters = job.get("parameters")
        if not isinstance(parameters, dict):
            mismatches.append("parameters")
        else:
            if parameters.get("aspect_ratio") != arm.aspect_ratio:
                mismatches.append("parameters.aspect_ratio")
            if parameters.get("number_of_images") != arm.requested_samples:
                mismatches.append("parameters.number_of_images")
            provenance = parameters.get("prompt_provenance")
            if arm.arm == ArmName.ENHANCED:
                if not isinstance(provenance, dict):
                    mismatches.append("parameters.prompt_provenance")
                else:
                    if provenance.get("enhancement_id") != arm.enhancement_id:
                        mismatches.append("prompt_provenance.enhancement_id")
                    if provenance.get("execution_prompt_sha256") != arm.execution_prompt_sha256:
                        mismatches.append("prompt_provenance.execution_prompt_sha256")
            elif provenance is not None:
                mismatches.append("raw.prompt_provenance")
        if mismatches:
            raise EvaluationRunnerError(
                f"Job contract mismatch for {arm.arm.value} arm: {', '.join(mismatches)}"
            )

    def _collect_assets(
        self,
        case_id: str,
        arm: ArmRecord,
        job: dict[str, Any],
    ) -> ArmRecord:
        assets = job.get("assets")
        if not isinstance(assets, list) or len(assets) != arm.requested_samples:
            raise EvaluationRunnerError(
                f"Completed job {arm.job_id} expected {arm.requested_samples} assets, "
                f"got {len(assets) if isinstance(assets, list) else 'non-list'}"
            )
        records: list[AssetRecord] = []
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                raise EvaluationRunnerError(f"Job {arm.job_id} returned a non-object asset")
            asset_id = _required_identifier(asset, "id", "asset")
            metadata = self.client.request_json(
                "GET",
                f"/api/assets/{asset_id}",
                expected_status=200,
                step_name=f"Asset metadata {asset_id}",
            )
            for field in ("id", "job_id", "kind", "mime", "size_bytes", "url"):
                if metadata.get(field) != asset.get(field):
                    raise EvaluationRunnerError(
                        f"Asset {asset_id} metadata mismatched field {field}"
                    )
            if metadata.get("job_id") != arm.job_id or metadata.get("kind") != "image":
                raise EvaluationRunnerError(f"Asset {asset_id} is not an image for job {arm.job_id}")
            mime = metadata.get("mime")
            if mime not in MIME_EXTENSIONS:
                raise EvaluationRunnerError(f"Asset {asset_id} has unsupported MIME type {mime!r}")
            url = metadata.get("url")
            if not isinstance(url, str) or not url.startswith("/files/"):
                raise EvaluationRunnerError(f"Asset {asset_id} has unsafe file URL")
            body, headers, _ = self.client.request_bytes(
                "GET",
                url,
                expected_status=200,
                step_name=f"Asset bytes {asset_id}",
            )
            size_bytes = metadata.get("size_bytes")
            if not isinstance(size_bytes, int) or size_bytes < 1 or len(body) != size_bytes:
                raise EvaluationRunnerError(f"Asset {asset_id} byte size did not match metadata")
            content_type = _header(headers, "Content-Type")
            if content_type and mime not in content_type:
                raise EvaluationRunnerError(f"Asset {asset_id} Content-Type did not match metadata")

            relative_path = (
                Path("images")
                / case_id
                / f"{arm.arm.value}-{index}{MIME_EXTENSIONS[mime]}"
            ).as_posix()
            _atomic_write_bytes(self.run_dir / relative_path, body)
            records.append(
                AssetRecord(
                    asset_id=asset_id,
                    job_id=arm.job_id,
                    sample_index=index,
                    relative_path=relative_path,
                    sha256=prompt_sha256_bytes(body),
                    media_type=mime,
                    byte_size=len(body),
                )
            )
        parameters = job.get("parameters")
        return arm.model_copy(
            update={
                "status": ArmStatus.COMPLETED,
                "generation_parameters": dict(parameters),
                "retry_count": _retry_count(job),
                "assets": tuple(records),
                "failure": None,
            }
        )

    def _record_terminal_failure(
        self,
        manifest: RunManifest,
        pair: PairRecord,
        arm: ArmRecord,
        job: dict[str, Any],
    ) -> RunManifest:
        failure = _failure_from_job(job)
        parameters = job.get("parameters")
        failed = arm.model_copy(
            update={
                "status": ArmStatus.FAILED,
                "generation_parameters": (
                    dict(parameters)
                    if isinstance(parameters, dict)
                    else dict(arm.generation_parameters)
                ),
                "retry_count": failure.retry_count,
                "assets": (),
                "failure": failure,
            }
        )
        pair = self._replace_arm(pair, failed)
        manifest = self._checkpoint_pair(
            manifest,
            pair,
            lifecycle=RunLifecycle.FAILED,
            last_error=failure,
        )
        cleanup_error: EvaluationRunnerError | None = None
        try:
            self._apply_cleanup_policy(manifest, pair, failed)
        except EvaluationRunnerError as exc:
            cleanup_error = exc
        cleanup_detail = f" Cleanup also failed: {cleanup_error}" if cleanup_error else ""
        raise GenerationFailedError(
            f"Generation {arm.job_id} failed with {failure.code}: "
            f"{failure.message}{cleanup_detail}"
        )

    def _apply_cleanup_policy(
        self,
        manifest: RunManifest,
        pair: PairRecord,
        arm: ArmRecord,
    ) -> RunManifest:
        if not arm.job_id:
            return manifest
        if self.config.keep_artifacts:
            if self._cleanup_state(arm.job_id) == BackendArtifactState.RETAINED:
                return manifest
            return self._set_cleanup_state(
                manifest,
                pair,
                arm,
                BackendArtifactState.RETAINED,
            )
        if self._cleanup_state(arm.job_id) == BackendArtifactState.DELETED:
            return manifest

        self.client.request_bytes(
            "DELETE",
            f"/api/generations/{arm.job_id}",
            expected_status={204, 404},
            step_name=f"Cleanup {arm.job_id}",
        )
        return self._set_cleanup_state(
            manifest,
            pair,
            arm,
            BackendArtifactState.DELETED,
        )

    def _sync_cleanup_artifact(self, manifest: RunManifest) -> RunManifest:
        if self.cleanup_path.exists():
            cleanup = load_cleanup_record(self.cleanup_path)
            if cleanup.run_id != self.config.run_id:
                raise EvaluationRunnerError("cleanup record run_id does not match manifest")
            policy = self._cleanup_policy()
            if cleanup.policy != policy:
                cleanup = CleanupRecord.model_validate(
                    cleanup.model_copy(update={"policy": policy}).model_dump()
                )
                write_cleanup_record(self.cleanup_path, cleanup)
        else:
            cleanup = CleanupRecord(
                schema_version=CURRENT_SCHEMA_VERSION,
                run_id=self.config.run_id,
                policy=self._cleanup_policy(),
                jobs=(),
            )
            write_cleanup_record(self.cleanup_path, cleanup)

        cleanup_hash = file_sha256(self.cleanup_path)
        if manifest.artifact_hashes.get("cleanup.json") == cleanup_hash:
            return manifest
        artifact_hashes = dict(manifest.artifact_hashes)
        artifact_hashes["cleanup.json"] = cleanup_hash
        updated = self._validated_manifest_copy(
            manifest,
            artifact_hashes=artifact_hashes,
            updated_at=self.now(),
        )
        write_run_manifest(self.manifest_path, updated)
        return updated

    def _set_cleanup_state(
        self,
        manifest: RunManifest,
        pair: PairRecord,
        arm: ArmRecord,
        state: BackendArtifactState,
    ) -> RunManifest:
        if not arm.job_id:
            raise EvaluationRunnerError("Cannot record cleanup state without job_id")
        cleanup = load_cleanup_record(self.cleanup_path)
        record = JobCleanupRecord(
            job_id=arm.job_id,
            case_id=pair.case_id,
            arm=arm.arm,
            state=state,
            updated_at=self.now(),
        )
        jobs = tuple(
            record if existing.job_id == arm.job_id else existing
            for existing in cleanup.jobs
        )
        if all(existing.job_id != arm.job_id for existing in cleanup.jobs):
            jobs = (*jobs, record)
        cleanup = CleanupRecord.model_validate(
            cleanup.model_copy(
                update={"policy": self._cleanup_policy(), "jobs": jobs}
            ).model_dump()
        )
        write_cleanup_record(self.cleanup_path, cleanup)
        artifact_hashes = dict(manifest.artifact_hashes)
        artifact_hashes["cleanup.json"] = file_sha256(self.cleanup_path)
        return self._checkpoint_pair(
            manifest,
            pair,
            artifact_hashes=artifact_hashes,
        )

    def _cleanup_state(self, job_id: str) -> BackendArtifactState | None:
        cleanup = load_cleanup_record(self.cleanup_path)
        for record in cleanup.jobs:
            if record.job_id == job_id:
                return record.state
        return None

    def _cleanup_policy(self) -> CleanupPolicy:
        return (
            CleanupPolicy.KEEP_BACKEND
            if self.config.keep_artifacts
            else CleanupPolicy.DELETE_BACKEND
        )

    def _verify_local_assets(self, arm: ArmRecord) -> None:
        for asset in arm.assets:
            path = (self.run_dir / asset.relative_path).resolve()
            try:
                path.relative_to(self.run_dir.resolve())
            except ValueError as exc:
                raise EvaluationRunnerError(
                    f"Completed asset path escaped the run directory: {asset.relative_path}"
                ) from exc
            if not path.is_file():
                raise EvaluationRunnerError(
                    f"Completed asset is missing and will not be regenerated automatically: "
                    f"{asset.relative_path}"
                )
            if path.stat().st_size != asset.byte_size or file_sha256(path) != asset.sha256:
                raise EvaluationRunnerError(
                    f"Completed asset hash/size mismatch: {asset.relative_path}"
                )

    def _checkpoint_pair(
        self,
        manifest: RunManifest,
        pair: PairRecord,
        *,
        lifecycle: RunLifecycle | None = None,
        last_error: FailureRecord | None | object = ...,
        artifact_hashes: dict[str, str] | None = None,
    ) -> RunManifest:
        pairs = tuple(
            pair if candidate.case_id == pair.case_id else candidate
            for candidate in manifest.pairs
        )
        updates: dict[str, Any] = {
            "pairs": pairs,
            "updated_at": self.now(),
        }
        if lifecycle is not None:
            updates["lifecycle"] = lifecycle
        if last_error is not ...:
            updates["last_error"] = last_error
        if artifact_hashes is not None:
            updates["artifact_hashes"] = artifact_hashes
        updated = self._validated_manifest_copy(manifest, **updates)
        write_run_manifest(self.manifest_path, updated)
        return updated

    @staticmethod
    def _validated_manifest_copy(manifest: RunManifest, **updates: Any) -> RunManifest:
        return RunManifest.model_validate(manifest.model_copy(update=updates).model_dump())

    @staticmethod
    def _replace_arm(pair: PairRecord, arm: ArmRecord) -> PairRecord:
        field = "raw" if arm.arm == ArmName.RAW else "enhanced"
        return PairRecord.model_validate(pair.model_copy(update={field: arm}).model_dump())

    @staticmethod
    def _pair(manifest: RunManifest, case_id: str) -> PairRecord:
        for pair in manifest.pairs:
            if pair.case_id == case_id:
                return pair
        raise EvaluationRunnerError(f"Manifest has no checkpoint for case {case_id}")


def _mock_metric_adapters() -> tuple[MetricAdapterConfig, ...]:
    return tuple(
        MetricAdapterConfig(
            metric=metric,
            adapter=f"mock_{metric.value}",
            model_revision="deterministic-v1",
            evidence_kind=EvidenceKind.SYNTHETIC,
            settings={},
        )
        for metric in MetricName
    )


def _required_text(payload: dict[str, Any], field: str, source: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationRunnerError(f"{source} response requires non-empty {field}")
    return value


def _required_identifier(payload: dict[str, Any], field: str, source: str) -> str:
    value = _required_text(payload, field, source)
    if not IDENTIFIER_RE.fullmatch(value):
        raise EvaluationRunnerError(f"{source} response contains invalid {field}")
    return value


def _retry_count(job: dict[str, Any]) -> int:
    attempts = job.get("attempts")
    return max(0, attempts - 1) if isinstance(attempts, int) else 0


def _failure_from_job(job: dict[str, Any]) -> FailureRecord:
    error = job.get("error")
    error = error if isinstance(error, dict) else {}
    code = error.get("code")
    if not isinstance(code, str) or not IDENTIFIER_RE.fullmatch(code):
        code = "generation_cancelled" if job.get("state") == "cancelled" else "generation_failed"
    message = error.get("message")
    if not isinstance(message, str) or not message.strip():
        message = "Generation was cancelled." if job.get("state") == "cancelled" else "Generation failed."
    return FailureRecord(
        code=code,
        message=message,
        retry_count=_retry_count(job),
        retryable=error.get("retryable") is True,
    )


def _header(headers: dict[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def prompt_sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_metadata() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if sha.returncode != 0 or not sha.stdout.strip():
        raise EvaluationRunnerError("Unable to determine Git SHA for run manifest")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        raise EvaluationRunnerError("Unable to determine Git worktree state")
    return sha.stdout.strip(), bool(status.stdout.strip())


def _default_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mock-{timestamp}-{uuid4().hex[:8]}"


def start_compose(env_file: Path) -> None:
    validate_mock_env_file(env_file)
    environment = os.environ.copy()
    environment["AI_PROVIDER"] = "mock"
    command = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "up",
        "-d",
        "--build",
        "db",
        "redis",
        "backend",
        "dispatcher",
        "worker",
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise EvaluationRunnerError(
            "Docker Compose failed while starting the mock evaluation services:\n"
            + result.stdout.strip()
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate resumable Raw/Enhanced image pairs through the mock HTTP API."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--poll-timeout-sec", type=float, default=60.0)
    parser.add_argument("--poll-interval-sec", type=float, default=1.0)
    parser.add_argument("--health-timeout-sec", type=float, default=60.0)
    parser.add_argument("--enhancer-model", default="gemini-2.5-flash")
    parser.add_argument("--template-version", default="v1")
    parser.add_argument("--compose", action="store_true")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env.example")
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help=(
            "Keep backend job/asset rows and files after local copies are verified. "
            "Local run artifacts and failure manifests are always preserved."
        ),
    )
    args = parser.parse_args(argv)

    try:
        require_mock_provider(os.environ)
        if args.compose:
            start_compose(args.env_file)
        git_sha, dirty_worktree = _git_metadata()
        config = RunnerConfig(
            base_url=args.base_url,
            benchmark_path=args.benchmark,
            runs_dir=args.runs_dir,
            run_id=args.run_id or _default_run_id(),
            keep_artifacts=args.keep_artifacts,
            poll_timeout_sec=args.poll_timeout_sec,
            poll_interval_sec=args.poll_interval_sec,
            expected_enhancer_model=args.enhancer_model,
            expected_template_version=args.template_version,
            git_sha=git_sha,
            dirty_worktree=dirty_worktree,
            health_timeout_sec=args.health_timeout_sec,
        )
        manifest = run_pairs(config)
    except EvaluationRunnerError as exc:
        print(f"PAIR RUN FAILED: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("PAIR RUN INTERRUPTED: submitted checkpoints are preserved for resume", file=sys.stderr)
        return 130

    print(
        f"PAIR RUN READY FOR SCORING: run_id={manifest.run_id} "
        f"cases={len(manifest.pairs)} evidence={manifest.evidence_kind.value}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
