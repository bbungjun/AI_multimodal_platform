from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol

from offline.offline_scorers import (
    build_real_adapter,
    canonical_evaluation_prompt,
    load_scorer_profile,
    metric_adapter_configs,
    resolve_device,
    validate_evaluation_inputs,
    validate_resources,
    verify_model_cache,
)
from schemas import (
    CURRENT_SCHEMA_VERSION,
    ArmStatus,
    EvidenceKind,
    MetricName,
    ProviderMode,
    RunLifecycle,
    RunManifest,
    ScoreRecord,
    file_sha256,
    load_pair_records,
    load_run_manifest,
    load_score_records,
    prompt_sha256,
    write_run_manifest,
    write_score_records,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNS_DIR = PACKAGE_ROOT / "runs"
DEFAULT_PILOT_PROFILE = PACKAGE_ROOT / "offline" / "scorer_profile.v2.json"
DEFAULT_CACHE_ROOT = Path(
    os.environ.get("SCORER_MODEL_CACHE", PACKAGE_ROOT / ".model-cache")
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RealScoringError(RuntimeError):
    """Raised when real Vertex image artifacts cannot be scored safely."""


class RealAdapter(Protocol):
    metric: MetricName
    adapter: str
    model_revision: str
    evidence_kind: EvidenceKind

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float: ...

    def close(self) -> None: ...


AdapterFactory = Callable[..., RealAdapter]


def score_real_run(
    run_dir: Path | str,
    *,
    profile_path: Path | str,
    cache_root: Path | str,
    requested_device: str,
    environ: Mapping[str, str],
    metrics: Sequence[MetricName] = tuple(MetricName),
    skip_resource_check: bool = False,
    adapter_factory: AdapterFactory = build_real_adapter,
    now: Callable[[], datetime] | None = None,
) -> list[ScoreRecord]:
    if environ.get("AI_PROVIDER") != ProviderMode.VERTEX.value:
        raise RealScoringError(
            "AI_PROVIDER=vertex is required for a real pilot manifest. "
            "The current value is not printed."
        )
    directory = Path(run_dir).resolve()
    manifest_path = directory / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    _validate_manifest(manifest)

    profile = load_scorer_profile(profile_path)
    benchmark_path = _safe_run_path(directory, manifest.benchmark_path)
    if not benchmark_path.is_file() or file_sha256(benchmark_path) != manifest.benchmark_sha256:
        raise RealScoringError("Benchmark snapshot is missing or does not match manifest")
    inputs = validate_evaluation_inputs(profile, benchmark_path)
    expected_configs = tuple(metric_adapter_configs(profile))
    if manifest.metric_adapters != expected_configs:
        raise RealScoringError("Manifest scorer provenance does not match pinned profile")

    verify_model_cache(profile, cache_root)
    device = resolve_device(requested_device)
    selected_metrics = tuple(dict.fromkeys(metrics))
    if not selected_metrics:
        raise RealScoringError("At least one metric must be selected")
    if not skip_resource_check:
        validate_resources(profile, device, selected_metrics)

    pairs_path = directory / "pairs.jsonl"
    _verify_recorded_hash(manifest, pairs_path, "pairs.jsonl")
    pairs = load_pair_records(pairs_path)
    if tuple(pairs) != manifest.pairs:
        raise RealScoringError("pairs.jsonl does not match manifest checkpoints")
    case_map = {case.case_id: case for case in inputs.cases}
    if set(case_map) != {pair.case_id for pair in pairs}:
        raise RealScoringError("Scorer profile and paired run case ids differ")

    scores_path = directory / "scores.jsonl"
    scores = load_score_records(scores_path) if scores_path.is_file() else []
    existing = _validate_existing_scores(scores, manifest)
    expected_keys = _expected_score_keys(pairs, selected_metrics)
    all_expected = _expected_score_keys(pairs, tuple(MetricName))
    unexpected = set(existing) - all_expected
    if unexpected:
        raise RealScoringError("Existing scores reference an unexpected case or asset")

    if manifest.lifecycle in {RunLifecycle.SUMMARIZING, RunLifecycle.COMPLETED}:
        if set(existing) != _expected_score_keys(pairs, tuple(MetricName)):
            raise RealScoringError("Completed scoring lifecycle has incomplete score records")
        _verify_recorded_hash(manifest, scores_path, "scores.jsonl")
        return scores
    if manifest.lifecycle != RunLifecycle.SCORING:
        raise RealScoringError(
            f"Run lifecycle must be scoring, got {manifest.lifecycle.value!r}"
        )

    for metric in selected_metrics:
        adapter = adapter_factory(
            metric,
            profile=profile,
            cache_root=cache_root,
            device=device,
            inputs=inputs,
        )
        try:
            if adapter.evidence_kind != EvidenceKind.REAL or adapter.metric != metric:
                raise RealScoringError(f"Adapter provenance is invalid for {metric.value}")
            for pair in sorted(pairs, key=lambda item: item.case_id):
                case = case_map[pair.case_id]
                evaluation_prompt = canonical_evaluation_prompt(case)
                evaluation_hash = prompt_sha256(evaluation_prompt)
                if pair.evaluation_prompt_sha256 != evaluation_hash:
                    raise RealScoringError(
                        f"Case {pair.case_id} canonical prompt hash does not match pair"
                    )
                for arm in (pair.raw, pair.enhanced):
                    if arm.status != ArmStatus.COMPLETED:
                        raise RealScoringError(
                            f"Case {pair.case_id} arm {arm.arm.value} is incomplete"
                        )
                    for asset in sorted(arm.assets, key=lambda item: item.sample_index):
                        key = (pair.case_id, arm.arm.value, asset.sha256, metric.value)
                        if key in existing:
                            continue
                        image_bytes = _verified_asset_bytes(directory, asset)
                        try:
                            value = adapter.score(evaluation_prompt, image_bytes)
                        except Exception as exc:
                            raise RealScoringError(
                                f"{metric.value} failed for {pair.case_id}/"
                                f"{arm.arm.value}/{asset.sample_index}: "
                                f"{type(exc).__name__}: {exc}"
                            ) from exc
                        record = ScoreRecord(
                            schema_version=CURRENT_SCHEMA_VERSION,
                            run_id=manifest.run_id,
                            case_id=pair.case_id,
                            arm=arm.arm,
                            asset_sha256=asset.sha256,
                            evaluation_prompt_sha256=evaluation_hash,
                            metric=metric,
                            score=value,
                            adapter=adapter.adapter,
                            model_revision=adapter.model_revision,
                            evidence_kind=EvidenceKind.REAL,
                        )
                        scores.append(record)
                        existing[key] = record
                        write_score_records(scores_path, scores)
        finally:
            adapter.close()

    if expected_keys - set(existing):
        return scores
    if set(existing) != all_expected:
        return scores

    artifact_hashes = dict(manifest.artifact_hashes)
    artifact_hashes["scores.jsonl"] = file_sha256(scores_path)
    updated = RunManifest.model_validate(
        manifest.model_copy(
            update={
                "lifecycle": RunLifecycle.SUMMARIZING,
                "updated_at": (now or _utc_now)(),
                "artifact_hashes": artifact_hashes,
            }
        ).model_dump()
    )
    write_run_manifest(manifest_path, updated)
    return scores


def _validate_manifest(manifest: RunManifest) -> None:
    if manifest.provider_mode != ProviderMode.VERTEX:
        raise RealScoringError("Real scoring requires a Vertex manifest")
    if manifest.evidence_kind != EvidenceKind.REAL:
        raise RealScoringError("Real scoring requires evidence_kind=real")


def _validate_existing_scores(
    scores: Sequence[ScoreRecord],
    manifest: RunManifest,
) -> dict[tuple[str, str, str, str], ScoreRecord]:
    configs = {config.metric: config for config in manifest.metric_adapters}
    existing: dict[tuple[str, str, str, str], ScoreRecord] = {}
    for score in scores:
        config = configs.get(score.metric)
        if score.run_id != manifest.run_id or score.evidence_kind != EvidenceKind.REAL:
            raise RealScoringError("Existing score provenance does not match run")
        if config is None or (
            score.adapter != config.adapter
            or score.model_revision != config.model_revision
        ):
            raise RealScoringError("Existing score does not match scorer profile")
        key = (
            score.case_id,
            score.arm.value,
            score.asset_sha256,
            score.metric.value,
        )
        if key in existing:
            raise RealScoringError("Existing scores contain a duplicate record")
        existing[key] = score
    return existing


def _expected_score_keys(
    pairs: Sequence[Any],
    metrics: Sequence[MetricName],
) -> set[tuple[str, str, str, str]]:
    return {
        (pair.case_id, arm.arm.value, asset.sha256, metric.value)
        for pair in pairs
        for arm in (pair.raw, pair.enhanced)
        for asset in arm.assets
        for metric in metrics
    }


def _verified_asset_bytes(directory: Path, asset: Any) -> bytes:
    path = _safe_run_path(directory, asset.relative_path)
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise RealScoringError(f"Cannot read asset {asset.relative_path}: {exc}") from exc
    if len(body) != asset.byte_size or hashlib.sha256(body).hexdigest() != asset.sha256:
        raise RealScoringError(f"Asset bytes do not match checkpoint: {asset.relative_path}")
    return body


def _safe_run_path(directory: Path, relative_path: str) -> Path:
    if PurePosixPath(relative_path).is_absolute() or PureWindowsPath(relative_path).is_absolute():
        raise RealScoringError("Artifact path must be relative")
    resolved = (directory / relative_path).resolve()
    try:
        resolved.relative_to(directory)
    except ValueError as exc:
        raise RealScoringError("Artifact path escaped the run directory") from exc
    return resolved


def _verify_recorded_hash(
    manifest: RunManifest,
    path: Path,
    relative_name: str,
) -> None:
    expected = manifest.artifact_hashes.get(relative_name)
    if expected is None or not path.is_file() or file_sha256(path) != expected:
        raise RealScoringError(f"{relative_name} is missing or does not match manifest")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a bounded Vertex pilot with pinned real offline adapters."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PILOT_PROFILE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--metric",
        action="append",
        choices=tuple(metric.value for metric in MetricName),
        dest="metrics",
    )
    parser.add_argument("--skip-resource-check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    if not RUN_ID_RE.fullmatch(arguments.run_id):
        print("REAL SCORING FAILED: invalid run-id", file=sys.stderr)
        return 2
    metrics = tuple(
        MetricName(value)
        for value in (arguments.metrics or [metric.value for metric in MetricName])
    )
    try:
        scores = score_real_run(
            arguments.runs_dir / arguments.run_id,
            profile_path=arguments.profile,
            cache_root=arguments.cache_dir,
            requested_device=arguments.device,
            environ=os.environ,
            metrics=metrics,
            skip_resource_check=arguments.skip_resource_check,
        )
    except (OSError, ValueError, RealScoringError) as exc:
        print(f"REAL SCORING FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "REAL OFFLINE PAIR SCORING CHECKPOINTED. "
        f"run_id={arguments.run_id} scores={len(scores)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
