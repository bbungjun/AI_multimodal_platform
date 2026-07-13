from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from schemas import MetricName, file_sha256

from offline.offline_scorers import (
    DEFAULT_BENCHMARK_PATH,
    DEFAULT_PROFILE_PATH,
    EVAL_ROOT,
    OfflineScorerError,
    ScorerProfile,
    build_real_adapter,
    calibrate_tie_threshold,
    canonical_evaluation_prompt,
    load_scorer_profile,
    metric_adapter_configs,
    prepare_model_cache,
    resolve_device,
    validate_evaluation_inputs,
    validate_resources,
    verify_model_cache,
)


DEFAULT_CACHE_ROOT = Path(
    os.environ.get("SCORER_MODEL_CACHE", EVAL_ROOT / ".model-cache")
)
DEFAULT_OUTPUT_DIR = EVAL_ROOT / "runs" / "offline-scorer-smoke-v1"


def run_smoke(
    *,
    profile_path: Path,
    benchmark_path: Path,
    cache_root: Path,
    output_dir: Path,
    requested_device: str,
    metrics: Sequence[MetricName],
    case_id: str | None,
    prepare_models: bool,
    prepare_only: bool,
    skip_resource_check: bool,
) -> Mapping[str, Any] | None:
    profile = load_scorer_profile(profile_path)
    inputs = validate_evaluation_inputs(profile, benchmark_path)
    if prepare_models:
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)
        prepare_model_cache(profile, cache_root)
    verify_model_cache(profile, cache_root)
    if prepare_only:
        return None

    selected_case_id = case_id or profile.data["calibration"]["fixture_case_id"]
    cases = {case.case_id: case for case in inputs.cases}
    if selected_case_id not in cases:
        raise OfflineScorerError(
            f"Smoke case {selected_case_id!r} is not an enabled benchmark case"
        )
    case = cases[selected_case_id]
    selected_metrics = tuple(dict.fromkeys(metrics))
    if not selected_metrics:
        raise OfflineScorerError("At least one metric must be selected")
    device = resolve_device(requested_device)
    if not skip_resource_check:
        validate_resources(profile, device, selected_metrics)

    destination = _safe_output_dir(output_dir)
    manifest_path = destination / "manifest.json"
    manifest_path.unlink(missing_ok=True)
    fixture_dir = destination / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    image_path = fixture_dir / f"{case.case_id}.png"
    _render_fixture(case.case_id).save(image_path, format="PNG", optimize=False)
    image_bytes = image_path.read_bytes()
    evaluation_prompt = canonical_evaluation_prompt(case)

    adapter_configs = {config.metric: config for config in metric_adapter_configs(profile)}
    score_artifact: dict[str, Any] = {
        "schema_version": 1,
        "case_id": case.case_id,
        "language": case.language.value,
        "evaluation_prompt": evaluation_prompt,
        "evaluation_prompt_sha256": _sha256_text(evaluation_prompt),
        "image_path": image_path.relative_to(destination).as_posix(),
        "image_sha256": file_sha256(image_path),
        "scores": {},
    }
    calibration_records: list[Mapping[str, Any]] = []
    repetitions = int(profile.data["calibration"]["repetitions"])
    for metric in selected_metrics:
        adapter = build_real_adapter(
            metric,
            profile=profile,
            cache_root=cache_root,
            device=device,
            inputs=inputs,
        )
        try:
            try:
                repeated_scores = [
                    adapter.score(evaluation_prompt, image_bytes)
                    for _ in range(repetitions)
                ]
            except OfflineScorerError:
                raise
            except Exception as exc:
                raise OfflineScorerError(
                    f"{metric.value} inference failed: {type(exc).__name__}: {exc}"
                ) from exc
            calibration = calibrate_tie_threshold(metric, repeated_scores, profile)
            score_entry: dict[str, Any] = {
                "score": repeated_scores[0],
                "adapter": adapter.adapter,
                "model_revision": adapter.model_revision,
                "evidence_kind": adapter.evidence_kind.value,
            }
            details = getattr(adapter, "last_question_details", ())
            if details:
                score_entry["question_details"] = list(details)
            score_artifact["scores"][metric.value] = score_entry
            calibration_records.append(calibration)
        finally:
            adapter.close()

    scores_path = destination / "smoke_scores.json"
    calibration_path = destination / "calibration.json"
    _atomic_json_write(scores_path, score_artifact)
    calibration_artifact = {
        "schema_version": 1,
        "profile_id": profile.profile_id,
        "profile_sha256": profile.sha256,
        "benchmark_sha256": file_sha256(benchmark_path),
        "fixture_case_id": case.case_id,
        "fixture_image_sha256": file_sha256(image_path),
        "device": device,
        "records": calibration_records,
        "freeze_before_provider_run": True,
    }
    _atomic_json_write(calibration_path, calibration_artifact)

    report_path = destination / "report.md"
    report = _render_report(
        profile,
        inputs.canonical_reviews,
        score_artifact,
        calibration_artifact,
        adapter_configs,
        device,
    )
    _atomic_text_write(report_path, report)

    manifest = {
        "schema_version": 1,
        "run_type": "offline_scorer_fixture_smoke",
        "evidence_kind": "real",
        "quality_claim_scope": "adapter_execution_only",
        "provider_calls": "none",
        "profile_id": profile.profile_id,
        "profile_path": profile.path.name,
        "profile_sha256": profile.sha256,
        "benchmark_path": Path(benchmark_path).name,
        "benchmark_sha256": file_sha256(benchmark_path),
        "canonical_prompt_review_sha256": profile.data["canonical_prompt_review"][
            "sha256"
        ],
        "tifa_questions_sha256": profile.data["metrics"]["tifa"][
            "questions_sha256"
        ],
        "device": device,
        "dtype": profile.data["resource_policy"][device]["dtype"],
        "metric_dtypes": profile.data["resource_policy"][device].get("dtypes"),
        "case_id": case.case_id,
        "metric_adapters": [
            adapter_configs[metric].model_dump(mode="json") for metric in selected_metrics
        ],
        "artifact_hashes": {
            image_path.relative_to(destination).as_posix(): file_sha256(image_path),
            "smoke_scores.json": file_sha256(scores_path),
            "calibration.json": file_sha256(calibration_path),
            "report.md": file_sha256(report_path),
        },
    }
    _atomic_json_write(manifest_path, manifest)
    return manifest


def _safe_output_dir(path: Path) -> Path:
    destination = path.expanduser().resolve()
    repo_root = EVAL_ROOT.parents[1].resolve()
    if repo_root == destination or repo_root in destination.parents:
        runs_root = (EVAL_ROOT / "runs").resolve()
        if destination != runs_root and runs_root not in destination.parents:
            raise OfflineScorerError(
                "Smoke output inside the repository must be under ignored "
                "evals/prompt_enhancement/runs/"
            )
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _render_fixture(case_id: str) -> Image.Image:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (512, 512), "#e9edf2")
    draw = ImageDraw.Draw(image)
    if case_id == "en-short-subject-001":
        draw.rectangle((0, 330, 512, 512), fill="#b78862")
        draw.ellipse((175, 250, 335, 315), fill="#2f6fb2")
        draw.rectangle((175, 280, 335, 405), fill="#2f6fb2")
        draw.ellipse((175, 370, 335, 430), fill="#25598e")
        draw.ellipse((300, 300, 395, 385), outline="#2f6fb2", width=24)
    elif case_id == "ko-short-subject-001":
        draw.rectangle((0, 0, 512, 512), fill="#687483")
        draw.polygon([(0, 512), (190, 190), (322, 190), (512, 512)], fill="#4d555f")
        for x in range(25, 500, 55):
            draw.line((x, 0, x - 45, 160), fill="#bfd6e6", width=3)
        draw.ellipse((115, 305, 230, 420), outline="#242b31", width=12)
        draw.ellipse((290, 305, 405, 420), outline="#242b31", width=12)
        draw.line((172, 362, 335, 362), fill="#c62f35", width=16)
        draw.line((172, 362, 260, 275), fill="#c62f35", width=16)
        draw.line((260, 275, 335, 362), fill="#c62f35", width=16)
        draw.line((260, 275, 320, 255), fill="#c62f35", width=12)
    elif case_id == "en-count-spatial-001":
        draw.rectangle((0, 0, 512, 512), fill="#d8c3a5")
        for center_x in (140, 285):
            draw.ellipse((center_x - 62, 190, center_x + 62, 285), fill="#f5f2ea", outline="#8a8378", width=6)
            draw.ellipse((center_x - 42, 205, center_x + 42, 258), fill="#c9d6d8")
        draw.rounded_rectangle((390, 145, 414, 390), radius=12, fill="#8b5a2b")
        draw.ellipse((370, 115, 435, 190), fill="#9d6732")
    elif case_id == "en-detailed-subject-001":
        draw.rectangle((0, 0, 512, 512), fill="#eee5d7")
        draw.rectangle((35, 45, 185, 265), fill="#fff6cf", outline="#a89b80", width=8)
        draw.rectangle((205, 235, 345, 420), fill="#6c7c75")
        draw.rounded_rectangle((185, 150, 365, 325), radius=30, fill="#7d8f87")
        draw.rectangle((390, 270, 500, 405), fill="#6f4328")
        draw.rectangle((375, 250, 512, 285), fill="#815238")
        draw.polygon([(35, 45), (185, 45), (365, 420), (250, 420)], fill="#f6edc7")
    else:
        raise OfflineScorerError(f"No deterministic fixture renderer for case {case_id}")
    return image


def _render_report(
    profile: ScorerProfile,
    canonical_reviews: Mapping[str, Mapping[str, Any]],
    scores: Mapping[str, Any],
    calibration: Mapping[str, Any],
    adapter_configs: Mapping[MetricName, Any],
    device: str,
) -> str:
    lines = [
        "# 실제 오프라인 scorer fixture smoke 보고서",
        "",
        "> 이 결과는 실제 scorer adapter와 고정 모델이 로컬 fixture에서 실행됐다는 근거다. "
        "Raw/Enhanced 생성 결과나 prompt enhancement 효과의 근거는 아니다.",
        "",
        f"- Profile: `{profile.profile_id}` (`{profile.sha256}`)",
        f"- Device/dtype: `{device}` / `{profile.data['resource_policy'][device]['dtype']}`",
        f"- Fixture case: `{scores['case_id']}`",
        f"- Provider 호출: 없음",
        "",
        "## 지표별 실행 결과",
        "",
        "| 지표 | fixture score | tie threshold | adapter | model revision |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    calibration_by_metric = {
        record["metric"]: record for record in calibration["records"]
    }
    for metric_name, score in scores["scores"].items():
        threshold = calibration_by_metric[metric_name]["tie_threshold"]
        lines.append(
            f"| {metric_name} | {score['score']:.12g} | {threshold:.12g} | "
            f"`{score['adapter']}` | `{score['model_revision']}` |"
        )
    lines.extend(["", "세 지표는 합산하지 않는다.", "", "## 한국어 canonical prompt 검토", ""])
    if not canonical_reviews:
        lines.append("활성화된 한국어 case가 없다.")
    else:
        for case_id, review in sorted(canonical_reviews.items()):
            lines.extend(
                [
                    f"### {case_id}",
                    "",
                    f"- 원문: {review['original_prompt']}",
                    f"- 검토된 영어 canonical prompt: {review['canonical_prompt_en']}",
                    f"- 상태/역할: `{review['status']}` / `{review['reviewer_role']}`",
                    f"- 검토 메모: {review['notes']}",
                    "",
                ]
            )
    lines.extend(["## 알려진 한계", ""])
    for metric in MetricName:
        if metric.value not in scores["scores"]:
            continue
        lines.append(
            f"- **{metric.value}:** {adapter_configs[metric].settings['limitations']}"
        )
    lines.extend(
        [
            "",
            "## Tie threshold 보정",
            "",
            f"고정 알고리즘 `{profile.data['calibration']['algorithm']}`으로 같은 fixture를 "
            f"{profile.data['calibration']['repetitions']}회 반복 평가했다. threshold는 "
            "`max(사전 정의 floor, 3 × median 대비 최대 절대 편차)`이며 Vertex 결과를 보기 "
            "전에 `calibration.json`으로 고정한다.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text_write(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _atomic_text_write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pinned real VQAScore, ImageReward, and TIFA adapters on a local fixture."
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH)
    parser.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--metric",
        action="append",
        choices=tuple(metric.value for metric in MetricName),
        dest="metrics",
        help="Metric to run; repeat to select multiple. Defaults to all three.",
    )
    parser.add_argument("--case-id")
    parser.add_argument("--prepare-models", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--skip-resource-check",
        action="store_true",
        help="Explicitly bypass RAM/VRAM guard; may terminate the container with OOM.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    metrics = tuple(
        MetricName(value) for value in (arguments.metrics or [metric.value for metric in MetricName])
    )
    try:
        manifest = run_smoke(
            profile_path=arguments.profile,
            benchmark_path=arguments.benchmark,
            cache_root=arguments.cache_dir,
            output_dir=arguments.output_dir,
            requested_device=arguments.device,
            metrics=metrics,
            case_id=arguments.case_id,
            prepare_models=arguments.prepare_models,
            prepare_only=arguments.prepare_only,
            skip_resource_check=arguments.skip_resource_check,
        )
    except (OSError, ValueError, OfflineScorerError) as exc:
        print(f"OFFLINE SCORER SMOKE FAILED: {exc}", file=sys.stderr)
        return 1
    if manifest is None:
        print("PINNED OFFLINE MODEL CACHE READY — NO PROVIDER CALLS")
        return 0
    print(
        "REAL OFFLINE SCORER SMOKE COMPLETE — ADAPTER EXECUTION EVIDENCE ONLY. "
        f"case_id={manifest['case_id']} metrics={len(manifest['metric_adapters'])} "
        f"device={manifest['device']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
