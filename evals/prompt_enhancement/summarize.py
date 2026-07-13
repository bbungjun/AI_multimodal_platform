from __future__ import annotations

import argparse
import math
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from schemas import (
    CURRENT_SCHEMA_VERSION,
    AggregateReport,
    ArmName,
    ArmStatus,
    CaseMetricRecord,
    EvidenceKind,
    MetricAggregate,
    MetricName,
    PairRecord,
    RunLifecycle,
    RunManifest,
    ScoreRecord,
    SliceAggregate,
    file_sha256,
    load_case_metric_records,
    load_pair_records,
    load_run_manifest,
    load_score_records,
    load_summary,
    write_case_metric_records,
    write_report_markdown,
    write_run_manifest,
    write_summary,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNS_DIR = PACKAGE_ROOT / "runs"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class SummaryError(RuntimeError):
    """Raised when mock scores cannot be summarized safely."""


def require_mock_provider(environ: Mapping[str, str]) -> None:
    if environ.get("AI_PROVIDER") != "mock":
        raise SummaryError(
            "AI_PROVIDER=mock is required. The summarizer does not load or accept a .env file."
        )


def summarize_run(
    run_dir: Path | str,
    *,
    environ: Mapping[str, str],
    now: Callable[[], datetime] | None = None,
) -> AggregateReport:
    require_mock_provider(environ)
    directory = Path(run_dir)
    manifest_path = directory / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    if manifest.evidence_kind != EvidenceKind.SYNTHETIC:
        raise SummaryError("Mock summary requires synthetic evidence")
    if manifest.lifecycle == RunLifecycle.COMPLETED:
        return _load_idempotent_summary(directory, manifest)
    if manifest.lifecycle != RunLifecycle.SUMMARIZING:
        raise SummaryError(
            f"Run lifecycle must be summarizing, got {manifest.lifecycle.value!r}"
        )

    pairs_path = directory / "pairs.jsonl"
    scores_path = directory / "scores.jsonl"
    _verify_recorded_hash(manifest, pairs_path, "pairs.jsonl")
    _verify_recorded_hash(manifest, scores_path, "scores.jsonl")
    pairs = load_pair_records(pairs_path)
    scores = load_score_records(scores_path)
    if tuple(pairs) != manifest.pairs:
        raise SummaryError("pairs.jsonl does not match manifest pair checkpoints")

    case_metrics, missing_cases = build_case_metrics(manifest, pairs, scores)
    if not case_metrics:
        raise SummaryError("No complete case has all three paired metric scores")

    generated_at = (now or _utc_now)()
    report = build_aggregate_report(
        manifest,
        pairs,
        case_metrics,
        missing_cases,
        generated_at=generated_at,
    )
    markdown = render_markdown_report(report, case_metrics)

    case_metrics_path = directory / "case_statistics.jsonl"
    summary_path = directory / "summary.json"
    report_path = directory / "report.md"
    write_case_metric_records(case_metrics_path, case_metrics)
    write_summary(summary_path, report)
    write_report_markdown(report_path, markdown)

    artifact_hashes = dict(manifest.artifact_hashes)
    for name, path in (
        ("case_statistics.jsonl", case_metrics_path),
        ("summary.json", summary_path),
        ("report.md", report_path),
    ):
        artifact_hashes[name] = file_sha256(path)
    completed = RunManifest.model_validate(
        manifest.model_copy(
            update={
                "lifecycle": RunLifecycle.COMPLETED,
                "updated_at": generated_at,
                "completed_at": generated_at,
                "artifact_hashes": artifact_hashes,
            }
        ).model_dump()
    )
    write_run_manifest(manifest_path, completed)
    return report


def build_case_metrics(
    manifest: RunManifest,
    pairs: Sequence[PairRecord],
    scores: Sequence[ScoreRecord],
) -> tuple[list[CaseMetricRecord], list[str]]:
    pair_map = {pair.case_id: pair for pair in pairs}
    adapter_map = {config.metric: config for config in manifest.metric_adapters}
    actual_counts: Counter[tuple[str, ArmName, str, MetricName]] = Counter()
    values: dict[tuple[str, ArmName, MetricName], list[float]] = defaultdict(list)

    for score in scores:
        pair = pair_map.get(score.case_id)
        if pair is None:
            raise SummaryError(f"Score references unknown case {score.case_id}")
        if score.run_id != manifest.run_id:
            raise SummaryError("Score run_id does not match manifest")
        if score.evidence_kind != EvidenceKind.SYNTHETIC:
            raise SummaryError("Every mock score must be marked synthetic")
        if score.evaluation_prompt_sha256 != pair.evaluation_prompt_sha256:
            raise SummaryError(
                f"Score for case {score.case_id} does not use the shared canonical prompt"
            )
        config = adapter_map[score.metric]
        if (
            score.adapter != config.adapter
            or score.model_revision != config.model_revision
            or score.evidence_kind != config.evidence_kind
        ):
            raise SummaryError(
                f"Score provenance does not match manifest for {score.metric.value}"
            )
        arm = pair.raw if score.arm == ArmName.RAW else pair.enhanced
        if score.asset_sha256 not in {asset.sha256 for asset in arm.assets}:
            raise SummaryError(
                f"Score references unknown {score.arm.value} asset for case {score.case_id}"
            )
        count_key = (score.case_id, score.arm, score.asset_sha256, score.metric)
        actual_counts[count_key] += 1
        values[(score.case_id, score.arm, score.metric)].append(score.score)

    records: list[CaseMetricRecord] = []
    missing_cases: list[str] = []
    for pair in sorted(pairs, key=lambda item: item.case_id):
        complete_arms = (
            pair.raw.status == ArmStatus.COMPLETED
            and pair.enhanced.status == ArmStatus.COMPLETED
        )
        expected_counts: Counter[tuple[str, ArmName, str, MetricName]] = Counter()
        if complete_arms:
            for arm in (pair.raw, pair.enhanced):
                for asset in arm.assets:
                    for metric in MetricName:
                        expected_counts[(pair.case_id, arm.arm, asset.sha256, metric)] += 1
        actual_for_case = Counter(
            {key: count for key, count in actual_counts.items() if key[0] == pair.case_id}
        )
        if not complete_arms or actual_for_case != expected_counts:
            missing_cases.append(pair.case_id)
            continue

        for metric in MetricName:
            raw_values = values[(pair.case_id, ArmName.RAW, metric)]
            enhanced_values = values[(pair.case_id, ArmName.ENHANCED, metric)]
            raw_mean = _stable_mean(raw_values)
            enhanced_mean = _stable_mean(enhanced_values)
            delta = _rounded(enhanced_mean - raw_mean)
            threshold = manifest.statistics.tie_thresholds[metric]
            outcome = (
                "win"
                if delta > threshold
                else "loss"
                if delta < -threshold
                else "tie"
            )
            records.append(
                CaseMetricRecord(
                    schema_version=CURRENT_SCHEMA_VERSION,
                    run_id=manifest.run_id,
                    case_id=pair.case_id,
                    language=pair.language,
                    category=pair.category,
                    metric=metric,
                    raw_sample_count=len(raw_values),
                    enhanced_sample_count=len(enhanced_values),
                    raw_mean=raw_mean,
                    enhanced_mean=enhanced_mean,
                    delta=delta,
                    tie_threshold=threshold,
                    outcome=outcome,
                )
            )
    return records, missing_cases


def build_aggregate_report(
    manifest: RunManifest,
    pairs: Sequence[PairRecord],
    case_metrics: Sequence[CaseMetricRecord],
    missing_cases: Sequence[str],
    *,
    generated_at: datetime,
) -> AggregateReport:
    complete_case_ids = {record.case_id for record in case_metrics}
    failed_case_count = sum(
        pair.raw.status == ArmStatus.FAILED or pair.enhanced.status == ArmStatus.FAILED
        for pair in pairs
    )
    metrics = tuple(
        _aggregate_metric(
            metric,
            [record for record in case_metrics if record.metric == metric],
            missing_case_count=len(missing_cases),
            seed=_derived_seed(manifest.statistics.bootstrap_seed, "overall", metric.value),
            resamples=manifest.statistics.bootstrap_resamples,
        )
        for metric in MetricName
    )

    slices: list[SliceAggregate] = []
    for dimension in ("language", "category"):
        values = sorted(
            {
                getattr(pair, dimension).value
                for pair in pairs
            }
        )
        for value in values:
            slice_case_ids = {
                pair.case_id
                for pair in pairs
                if getattr(pair, dimension).value == value
            }
            slice_records = [
                record for record in case_metrics if record.case_id in slice_case_ids
            ]
            if not slice_records:
                continue
            slice_missing = len(slice_case_ids - complete_case_ids)
            slices.append(
                SliceAggregate(
                    dimension=dimension,
                    value=value,
                    metrics=tuple(
                        _aggregate_metric(
                            metric,
                            [record for record in slice_records if record.metric == metric],
                            missing_case_count=slice_missing,
                            seed=_derived_seed(
                                manifest.statistics.bootstrap_seed,
                                dimension,
                                value,
                                metric.value,
                            ),
                            resamples=manifest.statistics.bootstrap_resamples,
                        )
                        for metric in MetricName
                    ),
                )
            )

    return AggregateReport(
        schema_version=CURRENT_SCHEMA_VERSION,
        run_id=manifest.run_id,
        evidence_kind=EvidenceKind.SYNTHETIC,
        generated_at=generated_at,
        completed_case_count=len(complete_case_ids),
        failed_case_count=failed_case_count,
        metrics=metrics,
        slices=tuple(slices),
        missing_cases=tuple(sorted(missing_cases)),
    )


def _aggregate_metric(
    metric: MetricName,
    records: Sequence[CaseMetricRecord],
    *,
    missing_case_count: int,
    seed: int,
    resamples: int,
) -> MetricAggregate:
    if not records:
        raise SummaryError(f"Metric {metric.value} has no complete case values")
    raw_means = [record.raw_mean for record in records]
    enhanced_means = [record.enhanced_mean for record in records]
    deltas = [record.delta for record in records]
    ci_low, ci_high = paired_bootstrap_ci(deltas, seed=seed, resamples=resamples)
    outcomes = Counter(record.outcome for record in records)
    return MetricAggregate(
        metric=metric,
        case_count=len(records),
        missing_case_count=missing_case_count,
        raw_mean=_stable_mean(raw_means),
        enhanced_mean=_stable_mean(enhanced_means),
        mean_delta=_stable_mean(deltas),
        median_delta=_rounded(statistics.median(deltas)),
        ci95_low=ci_low,
        ci95_high=ci_high,
        wins=outcomes["win"],
        ties=outcomes["tie"],
        losses=outcomes["loss"],
    )


def paired_bootstrap_ci(
    case_deltas: Sequence[float],
    *,
    seed: int,
    resamples: int,
) -> tuple[float, float]:
    if not case_deltas:
        raise SummaryError("Paired bootstrap requires at least one case delta")
    if resamples < 1:
        raise SummaryError("Paired bootstrap requires at least one resample")
    generator = random.Random(seed)
    sample_size = len(case_deltas)
    bootstrap_means = [
        _stable_mean(
            [case_deltas[generator.randrange(sample_size)] for _ in range(sample_size)]
        )
        for _ in range(resamples)
    ]
    bootstrap_means.sort()
    return (
        _rounded(_percentile(bootstrap_means, 0.025)),
        _rounded(_percentile(bootstrap_means, 0.975)),
    )


def render_markdown_report(
    report: AggregateReport,
    case_metrics: Sequence[CaseMetricRecord],
) -> str:
    lines = [
        f"# Prompt Enhancement Mock Evaluation — {report.run_id}",
        "",
        "> **SYNTHETIC MOCK EVIDENCE — 실제 이미지 품질 근거가 아닙니다.**",
        "> 이 결과는 평가 orchestration, artifact, paired 통계 흐름만 검증합니다.",
        "",
        f"- 완료 case: {report.completed_case_count}",
        f"- 실패 case: {report.failed_case_count}",
        f"- 누락 case: {len(report.missing_cases)}",
        "- 평가 기준: Raw와 Enhanced 모두 동일한 원본/canonical prompt",
        "- 지표 정책: VQAScore, ImageReward, TIFA를 각각 보고",
        "",
        "## 전체 paired 결과",
        "",
        _metric_table_header(),
    ]
    lines.extend(_metric_table_row(metric) for metric in report.metrics)
    lines.extend(
        [
            "",
            "## 프롬프트별 결과",
            "",
            "| Case | 언어 | Category | Metric | Raw mean | Enhanced mean | Delta | 판정 |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for record in case_metrics:
        lines.append(
            f"| {record.case_id} | {record.language.value} | {record.category.value} | "
            f"{record.metric.value} | {_format(record.raw_mean)} | "
            f"{_format(record.enhanced_mean)} | {_format(record.delta)} | "
            f"{record.outcome} |"
        )

    lines.extend(["", "## 언어/Category slice", ""])
    for slice_result in report.slices:
        lines.extend(
            [
                f"### {slice_result.dimension}: {slice_result.value}",
                "",
                _metric_table_header(),
            ]
        )
        lines.extend(_metric_table_row(metric) for metric in slice_result.metrics)
        lines.append("")

    lines.extend(["## 누락", ""])
    if report.missing_cases:
        lines.extend(f"- {case_id}" for case_id in report.missing_cases)
    else:
        lines.append("- 없음")
    return "\n".join(lines)


def _metric_table_header() -> str:
    return (
        "| Metric | Raw mean | Enhanced mean | Mean delta | Median delta | "
        "Paired bootstrap 95% CI | W/T/L | Missing |\n"
        "| --- | ---: | ---: | ---: | ---: | --- | --- | ---: |"
    )


def _metric_table_row(metric: MetricAggregate) -> str:
    return (
        f"| {metric.metric.value} | {_format(metric.raw_mean)} | "
        f"{_format(metric.enhanced_mean)} | {_format(metric.mean_delta)} | "
        f"{_format(metric.median_delta)} | [{_format(metric.ci95_low)}, "
        f"{_format(metric.ci95_high)}] | {metric.wins}/{metric.ties}/{metric.losses} | "
        f"{metric.missing_case_count} |"
    )


def _load_idempotent_summary(run_dir: Path, manifest: RunManifest) -> AggregateReport:
    for name in ("case_statistics.jsonl", "summary.json", "report.md"):
        _verify_recorded_hash(manifest, run_dir / name, name)
    records = load_case_metric_records(run_dir / "case_statistics.jsonl")
    if any(record.run_id != manifest.run_id for record in records):
        raise SummaryError("case_statistics.jsonl contains a different run_id")
    report = load_summary(run_dir / "summary.json")
    if report.run_id != manifest.run_id:
        raise SummaryError("summary.json contains a different run_id")
    return report


def _verify_recorded_hash(manifest: RunManifest, path: Path, relative_name: str) -> None:
    expected = manifest.artifact_hashes.get(relative_name)
    if expected is None:
        raise SummaryError(f"Manifest does not record {relative_name} hash")
    if not path.is_file() or file_sha256(path) != expected:
        raise SummaryError(f"{relative_name} is missing or does not match manifest hash")


def _stable_mean(values: Sequence[float]) -> float:
    if not values:
        raise SummaryError("Mean requires at least one value")
    return _rounded(math.fsum(values) / len(values))


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + (
        sorted_values[upper] - sorted_values[lower]
    ) * fraction


def _derived_seed(base_seed: int, *parts: str) -> int:
    value = base_seed
    for part in parts:
        for byte in part.encode("utf-8"):
            value = ((value * 131) + byte) & 0xFFFFFFFFFFFFFFFF
    return value


def _rounded(value: float) -> float:
    return round(value, 12)


def _format(value: float) -> str:
    return f"{value:.6f}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build paired mock statistics and a synthetic-evidence report."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    if not RUN_ID_RE.fullmatch(arguments.run_id):
        print("MOCK SUMMARY FAILED: invalid run-id", file=sys.stderr)
        return 2
    try:
        report = summarize_run(
            arguments.runs_dir / arguments.run_id,
            environ=os.environ,
        )
    except (OSError, ValueError, SummaryError) as exc:
        print(f"MOCK SUMMARY FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "SYNTHETIC MOCK REPORT ONLY — NOT IMAGE QUALITY EVIDENCE. "
        f"run_id={report.run_id} completed_cases={report.completed_case_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
