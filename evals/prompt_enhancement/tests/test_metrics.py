from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from schemas import (
    CURRENT_SCHEMA_VERSION,
    ArmName,
    ArmOrder,
    ArmRecord,
    ArmStatus,
    AssetRecord,
    EnhancerConfig,
    EvidenceKind,
    MetricAdapterConfig,
    MetricName,
    PairRecord,
    ProviderMode,
    RunLifecycle,
    RunManifest,
    ScoreRecord,
    StatisticsConfig,
    file_sha256,
    load_benchmark_cases,
    load_case_metric_records,
    load_run_manifest,
    prompt_sha256,
    write_pair_records,
    write_run_manifest,
    write_score_records,
)
from score_pairs import (
    ScoringError,
    build_mock_adapters,
    canonical_evaluation_prompt,
    require_mock_provider as require_mock_scoring,
    score_run,
)
from summarize import (
    SummaryError,
    paired_bootstrap_ci,
    require_mock_provider as require_mock_summary,
    summarize_run,
)


EVAL_ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc)


def _write_scoring_run(tmp_path: Path, *, run_id: str = "mock-metrics-001") -> Path:
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    benchmark_path = run_dir / "benchmark.jsonl"
    benchmark_path.write_bytes((EVAL_ROOT / "benchmark.v1.jsonl").read_bytes())
    cases = load_benchmark_cases(benchmark_path)
    pairs: list[PairRecord] = []

    for case_index, case in enumerate(cases):
        arms: dict[ArmName, ArmRecord] = {}
        raw_first = case_index % 2 == 0
        for arm_name in (ArmName.RAW, ArmName.ENHANCED):
            job_id = f"job-{case_index}-{arm_name.value}"
            assets: list[AssetRecord] = []
            for sample_index in range(case.samples_per_arm):
                relative_path = (
                    f"images/{case.case_id}/{arm_name.value}-{sample_index}.png"
                )
                body = (
                    f"synthetic-image:{case.case_id}:{arm_name.value}:{sample_index}"
                ).encode("utf-8")
                asset_path = run_dir / relative_path
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                asset_path.write_bytes(body)
                assets.append(
                    AssetRecord(
                        asset_id=f"asset-{case_index}-{arm_name.value}-{sample_index}",
                        job_id=job_id,
                        sample_index=sample_index,
                        relative_path=relative_path,
                        sha256=file_sha256(asset_path),
                        media_type="image/png",
                        byte_size=len(body),
                    )
                )
            execution_prompt = (
                case.original_prompt
                if arm_name == ArmName.RAW
                else f"{case.original_prompt} [enhanced draft]"
            )
            arms[arm_name] = ArmRecord(
                arm=arm_name,
                status=ArmStatus.COMPLETED,
                request_order=(
                    0
                    if (raw_first and arm_name == ArmName.RAW)
                    or (not raw_first and arm_name == ArmName.ENHANCED)
                    else 1
                ),
                execution_prompt=execution_prompt,
                execution_prompt_sha256=prompt_sha256(execution_prompt),
                enhancement_id=(
                    None
                    if arm_name == ArmName.RAW
                    else f"enhancement-{case_index}"
                ),
                job_id=job_id,
                target_model=case.target_model,
                aspect_ratio=case.aspect_ratio,
                requested_samples=case.samples_per_arm,
                generation_parameters={
                    "aspect_ratio": case.aspect_ratio,
                    "number_of_images": case.samples_per_arm,
                },
                assets=tuple(assets),
            )
        evaluation_prompt = canonical_evaluation_prompt(case)
        pairs.append(
            PairRecord(
                schema_version=CURRENT_SCHEMA_VERSION,
                run_id=run_id,
                case_id=case.case_id,
                language=case.language,
                category=case.category,
                evaluation_prompt_sha256=prompt_sha256(evaluation_prompt),
                arm_order=(
                    ArmOrder.RAW_FIRST if raw_first else ArmOrder.ENHANCED_FIRST
                ),
                raw=arms[ArmName.RAW],
                enhanced=arms[ArmName.ENHANCED],
            )
        )

    pairs_path = run_dir / "pairs.jsonl"
    write_pair_records(pairs_path, pairs)
    manifest = RunManifest(
        schema_version=CURRENT_SCHEMA_VERSION,
        run_id=run_id,
        lifecycle=RunLifecycle.SCORING,
        started_at=FIXED_TIME,
        updated_at=FIXED_TIME,
        completed_at=None,
        git_sha="f079f88",
        dirty_worktree=False,
        provider_mode=ProviderMode.MOCK,
        evidence_kind=EvidenceKind.SYNTHETIC,
        benchmark_path="benchmark.jsonl",
        benchmark_sha256=file_sha256(benchmark_path),
        enhancer=EnhancerConfig(
            model="mock-gemini",
            template_version="v1",
            template_sha256=prompt_sha256("template-version:v1"),
        ),
        generation_models=("imagen-4.0-fast-generate-001",),
        metric_adapters=tuple(
            MetricAdapterConfig(
                metric=metric,
                adapter=f"mock_{metric.value}",
                model_revision="deterministic-v1",
                evidence_kind=EvidenceKind.SYNTHETIC,
                settings={},
            )
            for metric in MetricName
        ),
        statistics=StatisticsConfig(
            bootstrap_seed=6100,
            bootstrap_resamples=250,
            tie_thresholds={metric: 0.05 for metric in MetricName},
        ),
        order_policy="alternating_by_case",
        pairs=tuple(pairs),
        artifact_hashes={
            "benchmark.jsonl": file_sha256(benchmark_path),
            "pairs.jsonl": file_sha256(pairs_path),
        },
        last_error=None,
    )
    write_run_manifest(run_dir / "manifest.json", manifest)
    return run_dir


def _replace_pair_hash(run_dir: Path, case_id: str, new_hash: str) -> None:
    manifest = load_run_manifest(run_dir / "manifest.json")
    pairs = [
        PairRecord.model_validate(
            pair.model_copy(
                update={"evaluation_prompt_sha256": new_hash}
                if pair.case_id == case_id
                else {}
            ).model_dump()
        )
        for pair in manifest.pairs
    ]
    pairs_path = run_dir / "pairs.jsonl"
    write_pair_records(pairs_path, pairs)
    hashes = dict(manifest.artifact_hashes)
    hashes["pairs.jsonl"] = file_sha256(pairs_path)
    updated = RunManifest.model_validate(
        manifest.model_copy(
            update={"pairs": tuple(pairs), "artifact_hashes": hashes}
        ).model_dump()
    )
    write_run_manifest(run_dir / "manifest.json", updated)


def _write_known_scores(run_dir: Path, *, omit_case: str | None = None) -> None:
    manifest = load_run_manifest(run_dir / "manifest.json")
    deltas = {
        "en-short-subject-001": 0.2,
        "ko-short-subject-001": 0.0,
        "en-count-spatial-001": -0.2,
        "en-detailed-subject-001": 0.1,
    }
    scores: list[ScoreRecord] = []
    for pair in manifest.pairs:
        if pair.case_id == omit_case:
            continue
        for arm in (pair.raw, pair.enhanced):
            for asset in arm.assets:
                for metric_index, metric in enumerate(MetricName):
                    raw_value = 0.2 + (metric_index * 0.1)
                    value = (
                        raw_value
                        if arm.arm == ArmName.RAW
                        else raw_value + deltas[pair.case_id]
                    )
                    config = next(
                        item for item in manifest.metric_adapters if item.metric == metric
                    )
                    scores.append(
                        ScoreRecord(
                            schema_version=CURRENT_SCHEMA_VERSION,
                            run_id=manifest.run_id,
                            case_id=pair.case_id,
                            arm=arm.arm,
                            asset_sha256=asset.sha256,
                            evaluation_prompt_sha256=pair.evaluation_prompt_sha256,
                            metric=metric,
                            score=value,
                            adapter=config.adapter,
                            model_revision=config.model_revision,
                            evidence_kind=EvidenceKind.SYNTHETIC,
                        )
                    )
    scores_path = run_dir / "scores.jsonl"
    write_score_records(scores_path, scores)
    hashes = dict(manifest.artifact_hashes)
    hashes["scores.jsonl"] = file_sha256(scores_path)
    updated = RunManifest.model_validate(
        manifest.model_copy(
            update={
                "lifecycle": RunLifecycle.SUMMARIZING,
                "artifact_hashes": hashes,
            }
        ).model_dump()
    )
    write_run_manifest(run_dir / "manifest.json", updated)


def test_mock_adapters_are_deterministic_separate_and_synthetic(tmp_path: Path):
    run_dir = _write_scoring_run(tmp_path)
    manifest = load_run_manifest(run_dir / "manifest.json")
    adapters = build_mock_adapters(manifest)

    first = [adapter.score("canonical prompt", b"image") for adapter in adapters]
    second = [adapter.score("canonical prompt", b"image") for adapter in adapters]

    assert first == second
    assert len(set(first)) == 3
    assert {adapter.metric for adapter in adapters} == set(MetricName)
    assert {adapter.evidence_kind for adapter in adapters} == {
        EvidenceKind.SYNTHETIC
    }


@dataclass
class RecordingAdapter:
    metric: MetricName
    adapter: str
    model_revision: str = "deterministic-v1"
    evidence_kind: EvidenceKind = EvidenceKind.SYNTHETIC
    prompts: list[str] | None = None

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        assert image_bytes
        assert self.prompts is not None
        self.prompts.append(evaluation_prompt)
        return 0.5


def test_score_run_uses_one_canonical_prompt_for_both_arms_and_is_idempotent(
    tmp_path: Path,
):
    run_dir = _write_scoring_run(tmp_path)
    shared_prompts: list[str] = []
    adapters = [
        RecordingAdapter(
            metric=metric,
            adapter=f"mock_{metric.value}",
            prompts=shared_prompts,
        )
        for metric in MetricName
    ]

    scores = score_run(
        run_dir,
        environ={"AI_PROVIDER": "mock"},
        adapters=adapters,
        now=lambda: FIXED_TIME,
    )
    first_bytes = (run_dir / "scores.jsonl").read_bytes()
    repeated = score_run(
        run_dir,
        environ={"AI_PROVIDER": "mock"},
        now=lambda: FIXED_TIME,
    )

    assert len(scores) == 48
    assert repeated == scores
    assert (run_dir / "scores.jsonl").read_bytes() == first_bytes
    assert "a red bicycle in a rainy Seoul alley" in shared_prompts
    assert all("[enhanced draft]" not in prompt for prompt in shared_prompts)
    for case_id in {score.case_id for score in scores}:
        hashes = {
            score.evaluation_prompt_sha256
            for score in scores
            if score.case_id == case_id
        }
        assert len(hashes) == 1
        assert {score.arm for score in scores if score.case_id == case_id} == set(
            ArmName
        )
    assert load_run_manifest(run_dir / "manifest.json").lifecycle == RunLifecycle.SUMMARIZING


def test_score_run_rejects_pair_that_changes_the_canonical_reference(tmp_path: Path):
    run_dir = _write_scoring_run(tmp_path)
    _replace_pair_hash(run_dir, "en-short-subject-001", "0" * 64)

    with pytest.raises(ScoringError, match="canonical evaluation prompt hash"):
        score_run(run_dir, environ={"AI_PROVIDER": "mock"})


def test_summary_uses_case_deltas_before_aggregate_and_writes_all_artifacts(
    tmp_path: Path,
):
    run_dir = _write_scoring_run(tmp_path)
    _write_known_scores(run_dir)

    report = summarize_run(
        run_dir,
        environ={"AI_PROVIDER": "mock"},
        now=lambda: FIXED_TIME,
    )
    case_metrics = load_case_metric_records(run_dir / "case_statistics.jsonl")
    manifest = load_run_manifest(run_dir / "manifest.json")

    assert len(case_metrics) == 12
    assert report.completed_case_count == 4
    assert report.missing_cases == ()
    assert {metric.metric for metric in report.metrics} == set(MetricName)
    for metric in report.metrics:
        assert metric.case_count == 4
        assert metric.raw_mean in {0.2, 0.3, 0.4}
        assert metric.mean_delta == pytest.approx(0.025)
        assert metric.median_delta == pytest.approx(0.05)
        assert (metric.wins, metric.ties, metric.losses) == (2, 1, 1)
    assert {item.dimension for item in report.slices} == {"language", "category"}
    korean_slice = next(
        item
        for item in report.slices
        if item.dimension == "language" and item.value == "ko"
    )
    assert all((metric.wins, metric.ties, metric.losses) == (0, 1, 0) for metric in korean_slice.metrics)
    assert manifest.lifecycle == RunLifecycle.COMPLETED
    assert manifest.completed_at == FIXED_TIME
    for artifact in (
        "scores.jsonl",
        "case_statistics.jsonl",
        "summary.json",
        "report.md",
    ):
        assert manifest.artifact_hashes[artifact] == file_sha256(run_dir / artifact)

    markdown = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "SYNTHETIC MOCK EVIDENCE" in markdown
    assert "실제 이미지 품질 근거가 아닙니다" in markdown
    assert "VQAScore, ImageReward, TIFA를 각각 보고" in markdown
    assert "Paired bootstrap 95% CI" in markdown
    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert "composite" not in summary_payload
    assert {item["metric"] for item in summary_payload["metrics"]} == {
        "vqascore",
        "image_reward",
        "tifa",
    }


def test_summary_is_byte_stable_and_reports_incomplete_case(tmp_path: Path):
    run_dir = _write_scoring_run(tmp_path)
    missing_case = "ko-short-subject-001"
    _write_known_scores(run_dir, omit_case=missing_case)

    first = summarize_run(
        run_dir,
        environ={"AI_PROVIDER": "mock"},
        now=lambda: FIXED_TIME,
    )
    artifact_bytes = {
        name: (run_dir / name).read_bytes()
        for name in ("case_statistics.jsonl", "summary.json", "report.md")
    }
    second = summarize_run(
        run_dir,
        environ={"AI_PROVIDER": "mock"},
        now=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert second == first
    assert first.completed_case_count == 3
    assert first.missing_cases == (missing_case,)
    assert all(metric.missing_case_count == 1 for metric in first.metrics)
    assert {
        name: (run_dir / name).read_bytes() for name in artifact_bytes
    } == artifact_bytes


def test_paired_bootstrap_is_deterministic_and_resamples_cases():
    deltas = [0.2, 0.0, -0.2, 0.1]

    first = paired_bootstrap_ci(deltas, seed=6100, resamples=500)
    second = paired_bootstrap_ci(deltas, seed=6100, resamples=500)

    assert first == second
    assert first[0] <= sum(deltas) / len(deltas) <= first[1]
    assert paired_bootstrap_ci([0.25], seed=1, resamples=10) == (0.25, 0.25)


@pytest.mark.parametrize(
    "guard",
    [require_mock_scoring, require_mock_summary],
)
def test_metric_commands_refuse_non_mock_provider(guard):
    with pytest.raises((ScoringError, SummaryError), match="AI_PROVIDER=mock"):
        guard({"AI_PROVIDER": "vertex"})


def test_metric_modules_do_not_import_provider_or_heavy_model_runtimes():
    source = "\n".join(
        (EVAL_ROOT / name).read_text(encoding="utf-8")
        for name in ("score_pairs.py", "summarize.py")
    )

    for forbidden in ("google.genai", "vertexai", "import torch", "transformers"):
        assert forbidden not in source
