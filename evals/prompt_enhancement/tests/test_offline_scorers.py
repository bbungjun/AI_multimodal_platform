from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from offline import offline_scorers
from offline.offline_scorers import (
    DEFAULT_BENCHMARK_PATH,
    DEFAULT_PROFILE_PATH,
    OfflineScorerError,
    calibrate_tie_threshold,
    load_scorer_profile,
    metric_adapter_configs,
    model_snapshot_path,
    validate_evaluation_inputs,
    validate_resources,
    verify_model_cache,
)
from offline import run_smoke as smoke_module
from schemas import EvidenceKind, MetricName


OFFLINE_ROOT = Path(__file__).resolve().parents[1] / "offline"


def test_profile_freezes_models_packages_and_evaluation_inputs() -> None:
    profile = load_scorer_profile()
    inputs = validate_evaluation_inputs(profile)

    assert profile.profile_id == "creativeops-offline-scorers-v1"
    assert len(inputs.cases) == 4
    assert sum(len(questions) for questions in inputs.questions_by_case.values()) == 14
    assert set(inputs.questions_by_case) == {case.case_id for case in inputs.cases}
    assert inputs.canonical_reviews["ko-short-subject-001"]["status"] == "reviewed"

    snapshots = profile.data["model_snapshots"]
    assert len(snapshots) == 7
    assert all(len(snapshot["revision"]) == 40 for snapshot in snapshots)
    assert all(snapshot["allow_patterns"] for snapshot in snapshots)
    assert {
        (package["name"], package["version"], package["install_mode"])
        for package in profile.data["packages"]
    } == {
        ("t2v-metrics", "3.0", "no-deps"),
        ("image-reward", "1.5", "no-deps"),
    }


def test_real_adapter_configs_record_auditable_provenance() -> None:
    profile = load_scorer_profile()
    configs = metric_adapter_configs(profile)

    assert {config.metric for config in configs} == set(MetricName)
    assert {config.evidence_kind for config in configs} == {EvidenceKind.REAL}
    assert all(config.settings["profile_sha256"] == profile.sha256 for config in configs)
    tifa = next(config for config in configs if config.metric == MetricName.TIFA)
    assert tifa.settings["questions_sha256"] == profile.data["metrics"]["tifa"][
        "questions_sha256"
    ]


def test_profile_rejects_changed_frozen_question_file(tmp_path: Path) -> None:
    for filename in (
        "scorer_profile.v1.json",
        "requirements-runtime.lock.txt",
        "requirements-adapters.lock.txt",
        "canonical_prompt_reviews.v1.json",
        "tifa_questions.v1.jsonl",
    ):
        (tmp_path / filename).write_bytes((OFFLINE_ROOT / filename).read_bytes())
    question_path = tmp_path / "tifa_questions.v1.jsonl"
    question_path.write_text(
        question_path.read_text(encoding="utf-8").replace(
            "What color is the cup?",
            "Which color is the cup?",
        ),
        encoding="utf-8",
    )

    with pytest.raises(OfflineScorerError, match="hash does not match"):
        load_scorer_profile(tmp_path / "scorer_profile.v1.json")


def test_canonical_review_is_bound_to_exact_benchmark_hash(tmp_path: Path) -> None:
    benchmark = tmp_path / "benchmark.v1.jsonl"
    benchmark.write_bytes(DEFAULT_BENCHMARK_PATH.read_bytes() + b"\n")
    profile = load_scorer_profile()

    with pytest.raises(OfflineScorerError, match="benchmark hash"):
        validate_evaluation_inputs(profile, benchmark)


def test_incomplete_model_cache_fails_before_importing_models(tmp_path: Path) -> None:
    profile = load_scorer_profile()
    torch_was_loaded = "torch" in sys.modules

    with pytest.raises(OfflineScorerError, match="explicit prepare step") as error:
        verify_model_cache(profile, tmp_path)

    assert "clip_flant5_xl@" in str(error.value)
    assert ("torch" in sys.modules) is torch_was_loaded


def test_complete_model_cache_requires_markers_and_payloads(tmp_path: Path) -> None:
    profile = load_scorer_profile()
    marker_name = profile.data["cache_policy"]["marker_filename"]
    for snapshot in profile.data["model_snapshots"]:
        destination = model_snapshot_path(tmp_path, snapshot)
        destination.mkdir(parents=True)
        (destination / "payload.bin").write_bytes(b"fixture")
        (destination / marker_name).write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "key": snapshot["key"],
                    "repo_id": snapshot["repo_id"],
                    "revision": snapshot["revision"],
                }
            ),
            encoding="utf-8",
        )

    verify_model_cache(profile, tmp_path)


def test_calibration_uses_preregistered_floor_and_repeat_noise() -> None:
    profile = load_scorer_profile()

    stable = calibrate_tie_threshold(
        MetricName.IMAGE_REWARD,
        [0.25, 0.25, 0.25],
        profile,
    )
    noisy = calibrate_tie_threshold(
        MetricName.VQA_SCORE,
        [0.49, 0.50, 0.51],
        profile,
    )

    assert stable["tie_threshold"] == 0.01
    assert noisy["tie_threshold"] == pytest.approx(0.03)
    assert noisy["algorithm"] == "repeat-max-deviation-v1"


def test_cpu_resource_guard_fails_with_actionable_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = load_scorer_profile()
    monkeypatch.setattr(offline_scorers, "_available_memory_gib", lambda: 7.5)

    with pytest.raises(OfflineScorerError, match="larger Docker memory limit or CUDA"):
        validate_resources(profile, "cpu", (MetricName.VQA_SCORE,))


class _FixtureImage:
    def save(self, path: Path, *, format: str, optimize: bool) -> None:
        assert format == "PNG"
        assert optimize is False
        path.write_bytes(b"deterministic-local-png-fixture")


class _FakeRealAdapter:
    evidence_kind = EvidenceKind.REAL

    def __init__(self, metric: MetricName) -> None:
        self.metric = metric
        self.adapter = f"offline_{metric.value}_test"
        self.model_revision = f"{metric.value}-revision"
        self.closed = False

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        assert evaluation_prompt == "a small blue cup on a desk"
        assert image_bytes == b"deterministic-local-png-fixture"
        return {
            MetricName.VQA_SCORE: 0.75,
            MetricName.IMAGE_REWARD: 0.5,
            MetricName.TIFA: 2 / 3,
        }[self.metric]

    def close(self) -> None:
        self.closed = True


def test_smoke_writes_real_evidence_calibration_and_separate_korean_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapters: list[_FakeRealAdapter] = []

    def build_adapter(metric: MetricName, **_: object) -> _FakeRealAdapter:
        adapter = _FakeRealAdapter(metric)
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(smoke_module, "verify_model_cache", lambda *_: None)
    monkeypatch.setattr(smoke_module, "resolve_device", lambda _: "cpu")
    monkeypatch.setattr(smoke_module, "validate_resources", lambda *_: None)
    monkeypatch.setattr(smoke_module, "build_real_adapter", build_adapter)
    monkeypatch.setattr(smoke_module, "_render_fixture", lambda _: _FixtureImage())

    output_dir = tmp_path / "offline-smoke"
    manifest = smoke_module.run_smoke(
        profile_path=DEFAULT_PROFILE_PATH,
        benchmark_path=DEFAULT_BENCHMARK_PATH,
        cache_root=tmp_path / "cache",
        output_dir=output_dir,
        requested_device="auto",
        metrics=tuple(MetricName),
        case_id=None,
        prepare_models=False,
        prepare_only=False,
        skip_resource_check=False,
    )

    assert manifest is not None
    assert manifest["provider_calls"] == "none"
    assert manifest["evidence_kind"] == "real"
    assert manifest["quality_claim_scope"] == "adapter_execution_only"
    assert len(manifest["metric_adapters"]) == 3
    assert all(adapter.closed for adapter in adapters)
    calibration = json.loads((output_dir / "calibration.json").read_text(encoding="utf-8"))
    thresholds = {
        record["metric"]: record["tie_threshold"] for record in calibration["records"]
    }
    assert thresholds == {"vqascore": 0.001, "image_reward": 0.01, "tifa": 0.0}
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "한국어 canonical prompt 검토" in report
    assert "비 내리는 서울 골목의 빨간 자전거" in report
    assert "세 지표는 합산하지 않는다" in report


def test_failed_smoke_removes_a_stale_success_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingAdapter(_FakeRealAdapter):
        def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
            raise OfflineScorerError("fixture inference failed")

    monkeypatch.setattr(smoke_module, "verify_model_cache", lambda *_: None)
    monkeypatch.setattr(smoke_module, "resolve_device", lambda _: "cpu")
    monkeypatch.setattr(smoke_module, "validate_resources", lambda *_: None)
    monkeypatch.setattr(
        smoke_module,
        "build_real_adapter",
        lambda metric, **_: FailingAdapter(metric),
    )
    monkeypatch.setattr(smoke_module, "_render_fixture", lambda _: _FixtureImage())

    output_dir = tmp_path / "offline-smoke"
    output_dir.mkdir()
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text('{"stale": true}\n', encoding="utf-8")

    with pytest.raises(OfflineScorerError, match="fixture inference failed"):
        smoke_module.run_smoke(
            profile_path=DEFAULT_PROFILE_PATH,
            benchmark_path=DEFAULT_BENCHMARK_PATH,
            cache_root=tmp_path / "cache",
            output_dir=output_dir,
            requested_device="auto",
            metrics=(MetricName.VQA_SCORE,),
            case_id=None,
            prepare_models=False,
            prepare_only=False,
            skip_resource_check=False,
        )

    assert not manifest_path.exists()


def test_offline_boundary_does_not_import_provider_modules() -> None:
    source = (OFFLINE_ROOT / "offline_scorers.py").read_text(encoding="utf-8")

    assert "google.genai" not in source
    assert "vertexai" not in source
    assert "backend.app" not in source
    assert "AI_PROVIDER" not in source
    assert "MPNetModel.from_pretrained" in source
    assert "AutoModel.from_pretrained" not in source
    assert 'torch.autocast(device_type="cpu", dtype=torch.bfloat16)' in source


def test_docker_boundary_uses_hash_locks_narrow_packages_and_non_root_user() -> None:
    dockerfile = (OFFLINE_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime_lock = (OFFLINE_ROOT / "requirements-runtime.lock.txt").read_text(
        encoding="utf-8"
    )
    adapter_lock = (OFFLINE_ROOT / "requirements-adapters.lock.txt").read_text(
        encoding="utf-8"
    )

    assert "--require-hashes" in dockerfile
    assert "--no-deps" in dockerfile
    assert "USER scorer" in dockerfile
    assert "torch @ https://download.pytorch.org/whl/cpu/" in runtime_lock
    assert "--hash=sha256:" in runtime_lock
    assert "image-reward==1.5" in adapter_lock
    assert "t2v-metrics==3.0" in adapter_lock
