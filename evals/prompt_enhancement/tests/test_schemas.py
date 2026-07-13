from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import (
    CURRENT_SCHEMA_VERSION,
    AggregateReport,
    ArtifactSchemaError,
    AssetRecord,
    ArmName,
    ArmRecord,
    ArmStatus,
    EvidenceKind,
    MetricAggregate,
    MetricName,
    RunLifecycle,
    ScoreRecord,
    SliceAggregate,
    file_sha256,
    load_benchmark_cases,
    load_pair_records,
    load_run_manifest,
    load_score_records,
    load_summary,
    prompt_sha256,
    write_benchmark_cases,
    write_pair_records,
    write_run_manifest,
    write_score_records,
    write_summary,
)


EVAL_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = EVAL_ROOT / "fixtures"
REPO_ROOT = EVAL_ROOT.parents[1]


def test_valid_benchmark_fixture_round_trips(tmp_path: Path):
    cases = load_benchmark_cases(FIXTURES / "benchmark.valid.v1.jsonl")

    assert len(cases) == 4
    assert load_benchmark_cases(EVAL_ROOT / "benchmark.v1.jsonl") == cases
    assert {case.language for case in cases} == {"en", "ko"}
    korean_case = next(case for case in cases if case.language == "ko")
    assert korean_case.evaluation_prompt_en
    assert korean_case.evaluation_prompt_en_reviewed is True

    output = tmp_path / "benchmark.v1.jsonl"
    write_benchmark_cases(output, cases)

    assert load_benchmark_cases(output) == cases
    assert all(
        json.loads(line)["schema_version"] == CURRENT_SCHEMA_VERSION
        for line in output.read_text(encoding="utf-8").splitlines()
    )


def test_valid_manifest_round_trips_as_resumable_checkpoint(tmp_path: Path):
    manifest = load_run_manifest(FIXTURES / "manifest.valid.v1.json")

    assert manifest.lifecycle == RunLifecycle.GENERATING_ENHANCED
    assert manifest.pairs[0].raw.status == ArmStatus.COMPLETED
    assert manifest.pairs[0].enhanced.status == ArmStatus.PLANNED
    assert manifest.benchmark_sha256 == file_sha256(
        FIXTURES / "benchmark.valid.v1.jsonl"
    )

    resumed = manifest.model_copy(
        update={
            "lifecycle": RunLifecycle.COLLECTING_ASSETS,
            "updated_at": datetime(2026, 7, 13, 7, 5, tzinfo=timezone.utc),
        }
    )
    output = tmp_path / "run" / "manifest.json"
    write_run_manifest(output, resumed)

    assert load_run_manifest(output) == resumed
    assert list(output.parent.glob("*.tmp")) == []


@pytest.mark.parametrize(
    ("filename", "payload", "artifact_kind"),
    [
        (
            "benchmark.jsonl",
            '{"schema_version":2,"case_id":"future"}\n',
            "benchmark case",
        ),
        (
            "manifest.json",
            '{"schema_version":2,"run_id":"future"}',
            "run manifest",
        ),
    ],
)
def test_incompatible_schema_version_fails_with_actionable_error(
    tmp_path: Path,
    filename: str,
    payload: str,
    artifact_kind: str,
):
    path = tmp_path / filename
    path.write_text(payload, encoding="utf-8")

    loader = load_benchmark_cases if filename.endswith("jsonl") else load_run_manifest
    with pytest.raises(
        ArtifactSchemaError,
        match=rf"Unsupported {artifact_kind} schema_version 2.*supported version is 1",
    ):
        loader(path)


def test_invalid_manifest_reports_path_and_invalid_field(tmp_path: Path):
    payload = json.loads(
        (FIXTURES / "manifest.valid.v1.json").read_text(encoding="utf-8")
    )
    payload["unexpected_secret"] = "must not be accepted"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactSchemaError) as exc_info:
        load_run_manifest(path)

    message = str(exc_info.value)
    assert str(path) in message
    assert "unexpected_secret" in message
    assert "Extra inputs are not permitted" in message


def test_manifest_rejects_duplicate_case_checkpoints(tmp_path: Path):
    payload = json.loads(
        (FIXTURES / "manifest.valid.v1.json").read_text(encoding="utf-8")
    )
    payload["pairs"].append(payload["pairs"][0])
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactSchemaError, match="duplicate case_id"):
        load_run_manifest(path)


def test_arm_rejects_execution_prompt_hash_mismatch():
    with pytest.raises(ValidationError, match="execution_prompt_sha256"):
        ArmRecord(
            arm=ArmName.RAW,
            status=ArmStatus.PLANNED,
            request_order=0,
            execution_prompt="a small blue cup",
            execution_prompt_sha256="0" * 64,
            target_model="imagen-4.0-fast-generate-001",
            aspect_ratio="1:1",
            requested_samples=2,
        )


def test_arm_preserves_nested_generation_provenance():
    prompt = "a small blue cup"
    arm = ArmRecord(
        arm=ArmName.ENHANCED,
        status=ArmStatus.PLANNED,
        request_order=1,
        execution_prompt=prompt,
        execution_prompt_sha256=prompt_sha256(prompt),
        enhancement_id="enhancement-1",
        target_model="imagen-4.0-fast-generate-001",
        aspect_ratio="1:1",
        requested_samples=2,
        generation_parameters={
            "prompt_provenance": {
                "source": "enhancement",
                "edited_after_enhancement": True,
                "hashes": ["original", "draft", "execution"],
            }
        },
    )

    assert arm.generation_parameters["prompt_provenance"] == {
        "source": "enhancement",
        "edited_after_enhancement": True,
        "hashes": ["original", "draft", "execution"],
    }


def test_submitted_enhanced_arm_requires_enhancement_provenance():
    prompt = "a small blue cup"

    with pytest.raises(ValidationError, match="requires enhancement_id"):
        ArmRecord(
            arm=ArmName.ENHANCED,
            status=ArmStatus.SUBMITTED,
            request_order=1,
            execution_prompt=prompt,
            execution_prompt_sha256=prompt_sha256(prompt),
            job_id="job-enhanced-1",
            target_model="imagen-4.0-fast-generate-001",
            aspect_ratio="1:1",
            requested_samples=2,
        )


def test_asset_rejects_absolute_or_parent_traversal_paths():
    base = {
        "asset_id": "asset-1",
        "job_id": "job-1",
        "sample_index": 0,
        "sha256": "a" * 64,
        "media_type": "image/png",
        "byte_size": 128,
    }

    for unsafe_path in (
        "C:/Users/example/private.png",
        "C:Users/example/private.png",
        "/home/example/private.png",
        "images/../private.png",
    ):
        with pytest.raises(ValidationError, match="relative artifact path"):
            AssetRecord(relative_path=unsafe_path, **base)


def test_summary_schema_round_trips(tmp_path: Path):
    generated_at = datetime(2026, 7, 13, 8, 0, tzinfo=timezone.utc)
    metric = MetricAggregate(
        metric=MetricName.VQA_SCORE,
        case_count=4,
        missing_case_count=0,
        raw_mean=0.4,
        enhanced_mean=0.5,
        mean_delta=0.1,
        median_delta=0.1,
        ci95_low=0.02,
        ci95_high=0.18,
        wins=3,
        ties=1,
        losses=0,
    )
    report = AggregateReport(
        schema_version=CURRENT_SCHEMA_VERSION,
        run_id="mock-20260713-001",
        evidence_kind=EvidenceKind.SYNTHETIC,
        generated_at=generated_at,
        completed_case_count=4,
        failed_case_count=0,
        metrics=[metric],
        slices=[
            SliceAggregate(
                dimension="language",
                value="ko",
                metrics=[metric],
            )
        ],
        missing_cases=[],
    )
    output = tmp_path / "summary.json"

    write_summary(output, report)

    assert load_summary(output) == report


def test_pair_and_score_jsonl_round_trip(tmp_path: Path):
    manifest = load_run_manifest(FIXTURES / "manifest.valid.v1.json")
    pair_path = tmp_path / "pairs.jsonl"
    write_pair_records(pair_path, list(manifest.pairs))

    pairs = load_pair_records(pair_path)
    assert pairs == list(manifest.pairs)

    raw_asset = pairs[0].raw.assets[0]
    score = ScoreRecord(
        schema_version=CURRENT_SCHEMA_VERSION,
        run_id=manifest.run_id,
        case_id=pairs[0].case_id,
        arm=ArmName.RAW,
        asset_sha256=raw_asset.sha256,
        evaluation_prompt_sha256=pairs[0].evaluation_prompt_sha256,
        metric=MetricName.VQA_SCORE,
        score=0.5,
        adapter="mock_vqascore",
        model_revision="deterministic-v1",
        evidence_kind=EvidenceKind.SYNTHETIC,
    )
    score_path = tmp_path / "scores.jsonl"
    write_score_records(score_path, [score])

    assert load_score_records(score_path) == [score]


def test_run_and_model_cache_directories_are_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "evals/prompt_enhancement/runs/" in gitignore
    assert "evals/prompt_enhancement/.model-cache/" in gitignore


def test_prompt_hash_preserves_exact_text():
    assert prompt_sha256("blue cup") != prompt_sha256("blue cup ")
