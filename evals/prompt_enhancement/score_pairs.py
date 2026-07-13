from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from schemas import (
    CURRENT_SCHEMA_VERSION,
    ArmName,
    ArmStatus,
    BenchmarkCase,
    EvidenceKind,
    MetricAdapterConfig,
    MetricName,
    ProviderMode,
    RunLifecycle,
    RunManifest,
    ScoreRecord,
    file_sha256,
    load_benchmark_cases,
    load_pair_records,
    load_run_manifest,
    load_score_records,
    prompt_sha256,
    write_run_manifest,
    write_score_records,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNS_DIR = PACKAGE_ROOT / "runs"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ScoringError(RuntimeError):
    """Raised when a paired run cannot be scored safely."""


class ScorerAdapter(Protocol):
    metric: MetricName
    adapter: str
    model_revision: str
    evidence_kind: EvidenceKind

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        """Return one finite score for one canonical prompt/image pair."""


@dataclass(frozen=True)
class _DeterministicMockAdapter:
    config: MetricAdapterConfig

    @property
    def metric(self) -> MetricName:
        return self.config.metric

    @property
    def adapter(self) -> str:
        return self.config.adapter

    @property
    def model_revision(self) -> str:
        return self.config.model_revision

    @property
    def evidence_kind(self) -> EvidenceKind:
        return self.config.evidence_kind

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        settings = json.dumps(
            self.config.settings,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(
            b"creativeops-synthetic-metric-v1\0"
            + self.metric.value.encode("ascii")
            + b"\0"
            + self.model_revision.encode("utf-8")
            + b"\0"
            + settings.encode("utf-8")
            + b"\0"
            + evaluation_prompt.encode("utf-8")
            + b"\0"
            + image_bytes
        ).digest()
        unit_value = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
        return round(self._map_unit_value(unit_value), 12)

    def _map_unit_value(self, value: float) -> float:
        raise NotImplementedError


class MockVQAScoreAdapter(_DeterministicMockAdapter):
    def _map_unit_value(self, value: float) -> float:
        return value


class MockImageRewardAdapter(_DeterministicMockAdapter):
    def _map_unit_value(self, value: float) -> float:
        return (2.0 * value) - 1.0


class MockTIFAAdapter(_DeterministicMockAdapter):
    def _map_unit_value(self, value: float) -> float:
        return value


ADAPTER_TYPES: dict[MetricName, type[_DeterministicMockAdapter]] = {
    MetricName.VQA_SCORE: MockVQAScoreAdapter,
    MetricName.IMAGE_REWARD: MockImageRewardAdapter,
    MetricName.TIFA: MockTIFAAdapter,
}


def require_mock_provider(environ: Mapping[str, str]) -> None:
    if environ.get("AI_PROVIDER") != "mock":
        raise ScoringError(
            "AI_PROVIDER=mock is required. The scorer does not load or accept a .env file."
        )


def build_mock_adapters(manifest: RunManifest) -> tuple[ScorerAdapter, ...]:
    adapters: list[ScorerAdapter] = []
    for config in sorted(manifest.metric_adapters, key=lambda item: item.metric.value):
        expected_name = f"mock_{config.metric.value}"
        if config.adapter != expected_name:
            raise ScoringError(
                f"Metric {config.metric.value} requires adapter={expected_name!r} in mock mode"
            )
        if config.model_revision != "deterministic-v1":
            raise ScoringError(
                f"Metric {config.metric.value} requires model_revision='deterministic-v1'"
            )
        if config.evidence_kind != EvidenceKind.SYNTHETIC:
            raise ScoringError("Mock metric adapters must use synthetic evidence")
        adapters.append(ADAPTER_TYPES[config.metric](config))
    return tuple(adapters)


def canonical_evaluation_prompt(case: BenchmarkCase) -> str:
    if case.evaluation_prompt_en_reviewed and case.evaluation_prompt_en:
        return case.evaluation_prompt_en
    return case.evaluation_prompt


def score_run(
    run_dir: Path | str,
    *,
    environ: Mapping[str, str],
    adapters: Sequence[ScorerAdapter] | None = None,
    now: Callable[[], datetime] | None = None,
) -> list[ScoreRecord]:
    require_mock_provider(environ)
    directory = Path(run_dir)
    manifest_path = directory / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    _validate_manifest_mode(manifest)

    scores_path = directory / "scores.jsonl"
    if manifest.lifecycle in {RunLifecycle.SUMMARIZING, RunLifecycle.COMPLETED}:
        return _load_idempotent_scores(directory, manifest, scores_path)
    if manifest.lifecycle != RunLifecycle.SCORING:
        raise ScoringError(
            f"Run lifecycle must be scoring, got {manifest.lifecycle.value!r}"
        )

    benchmark_path = _safe_run_path(directory, manifest.benchmark_path)
    if file_sha256(benchmark_path) != manifest.benchmark_sha256:
        raise ScoringError("Benchmark snapshot hash does not match manifest")
    cases = {
        case.case_id: case
        for case in load_benchmark_cases(benchmark_path)
        if case.enabled
    }

    pairs_path = directory / "pairs.jsonl"
    _verify_recorded_hash(manifest, pairs_path, "pairs.jsonl")
    pairs = load_pair_records(pairs_path)
    if tuple(pairs) != manifest.pairs:
        raise ScoringError("pairs.jsonl does not match manifest pair checkpoints")
    if set(cases) != {pair.case_id for pair in pairs}:
        raise ScoringError("Benchmark snapshot and pair case ids do not match")

    scorer_adapters = tuple(adapters or build_mock_adapters(manifest))
    _validate_adapter_set(scorer_adapters, manifest)
    scores: list[ScoreRecord] = []
    for pair in sorted(pairs, key=lambda item: item.case_id):
        case = cases[pair.case_id]
        evaluation_prompt = canonical_evaluation_prompt(case)
        evaluation_hash = prompt_sha256(evaluation_prompt)
        if pair.evaluation_prompt_sha256 != evaluation_hash:
            raise ScoringError(
                f"Case {pair.case_id} canonical evaluation prompt hash does not match pair"
            )
        for arm in (pair.raw, pair.enhanced):
            if arm.status != ArmStatus.COMPLETED:
                raise ScoringError(
                    f"Case {pair.case_id} arm {arm.arm.value} is not completed"
                )
            for asset in sorted(arm.assets, key=lambda item: item.sample_index):
                asset_path = _safe_run_path(directory, asset.relative_path)
                image_bytes = asset_path.read_bytes()
                if len(image_bytes) != asset.byte_size:
                    raise ScoringError(
                        f"Asset size does not match checkpoint: {asset.relative_path}"
                    )
                if hashlib.sha256(image_bytes).hexdigest() != asset.sha256:
                    raise ScoringError(
                        f"Asset hash does not match checkpoint: {asset.relative_path}"
                    )
                for adapter in scorer_adapters:
                    scores.append(
                        ScoreRecord(
                            schema_version=CURRENT_SCHEMA_VERSION,
                            run_id=manifest.run_id,
                            case_id=pair.case_id,
                            arm=arm.arm,
                            asset_sha256=asset.sha256,
                            evaluation_prompt_sha256=evaluation_hash,
                            metric=adapter.metric,
                            score=adapter.score(evaluation_prompt, image_bytes),
                            adapter=adapter.adapter,
                            model_revision=adapter.model_revision,
                            evidence_kind=adapter.evidence_kind,
                        )
                    )

    write_score_records(scores_path, scores)
    artifact_hashes = dict(manifest.artifact_hashes)
    artifact_hashes["scores.jsonl"] = file_sha256(scores_path)
    updated_at = (now or _utc_now)()
    updated = RunManifest.model_validate(
        manifest.model_copy(
            update={
                "lifecycle": RunLifecycle.SUMMARIZING,
                "updated_at": updated_at,
                "artifact_hashes": artifact_hashes,
            }
        ).model_dump()
    )
    write_run_manifest(manifest_path, updated)
    return scores


def _validate_manifest_mode(manifest: RunManifest) -> None:
    if manifest.provider_mode != ProviderMode.MOCK:
        raise ScoringError("Only mock provider manifests are supported by this scorer")
    if manifest.evidence_kind != EvidenceKind.SYNTHETIC:
        raise ScoringError("Mock scoring requires synthetic evidence")


def _validate_adapter_set(
    adapters: Sequence[ScorerAdapter],
    manifest: RunManifest,
) -> None:
    by_metric = {adapter.metric: adapter for adapter in adapters}
    if set(by_metric) != set(MetricName) or len(adapters) != len(MetricName):
        raise ScoringError(
            "Scorer adapters must define vqascore, image_reward, and tifa exactly once"
        )
    configured = {config.metric: config for config in manifest.metric_adapters}
    for metric, adapter in by_metric.items():
        config = configured[metric]
        if (
            adapter.adapter != config.adapter
            or adapter.model_revision != config.model_revision
            or adapter.evidence_kind != config.evidence_kind
        ):
            raise ScoringError(
                f"Metric adapter provenance does not match manifest for {metric.value}"
            )


def _load_idempotent_scores(
    run_dir: Path,
    manifest: RunManifest,
    scores_path: Path,
) -> list[ScoreRecord]:
    _verify_recorded_hash(manifest, scores_path, "scores.jsonl")
    scores = load_score_records(scores_path)
    if any(score.run_id != manifest.run_id for score in scores):
        raise ScoringError("scores.jsonl contains a different run_id")
    return scores


def _verify_recorded_hash(manifest: RunManifest, path: Path, relative_name: str) -> None:
    expected = manifest.artifact_hashes.get(relative_name)
    if expected is None:
        raise ScoringError(f"Manifest does not record {relative_name} hash")
    if not path.is_file() or file_sha256(path) != expected:
        raise ScoringError(f"{relative_name} is missing or does not match manifest hash")


def _safe_run_path(run_dir: Path, relative_path: str) -> Path:
    path = (run_dir / relative_path).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise ScoringError(f"Artifact path escaped the run directory: {relative_path}") from exc
    if not path.is_file():
        raise ScoringError(f"Required artifact is missing: {relative_path}")
    return path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a completed mock paired-generation run with synthetic metrics."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    if not RUN_ID_RE.fullmatch(arguments.run_id):
        print("MOCK SCORING FAILED: invalid run-id", file=sys.stderr)
        return 2
    try:
        scores = score_run(
            arguments.runs_dir / arguments.run_id,
            environ=os.environ,
        )
    except (OSError, ValueError, ScoringError) as exc:
        print(f"MOCK SCORING FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "SYNTHETIC MOCK SCORES ONLY — NOT IMAGE QUALITY EVIDENCE. "
        f"run_id={arguments.run_id} score_records={len(scores)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
