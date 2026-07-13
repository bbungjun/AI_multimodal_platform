from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


CURRENT_SCHEMA_VERSION = 1
ALL_METRICS = {"vqascore", "image_reward", "tifa"}


class ArtifactSchemaError(ValueError):
    """Raised when a versioned evaluation artifact cannot be loaded safely."""


class BenchmarkLanguage(StrEnum):
    ENGLISH = "en"
    KOREAN = "ko"


class BenchmarkCategory(StrEnum):
    SHORT_SUBJECT = "short_subject"
    DETAILED_SUBJECT = "detailed_subject"
    MULTI_OBJECT = "multi_object"
    COUNT_SPATIAL = "count_spatial"
    STYLE_LIGHTING = "style_lighting"


class CreativityPreset(StrEnum):
    FAITHFUL = "faithful"
    BALANCED = "balanced"
    IMAGINATIVE = "imaginative"


class ProviderMode(StrEnum):
    MOCK = "mock"
    VERTEX = "vertex"


class EvidenceKind(StrEnum):
    SYNTHETIC = "synthetic"
    REAL = "real"


class RunLifecycle(StrEnum):
    PLANNED = "planned"
    ENHANCING = "enhancing"
    GENERATING_RAW = "generating_raw"
    GENERATING_ENHANCED = "generating_enhanced"
    COLLECTING_ASSETS = "collecting_assets"
    SCORING = "scoring"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"


class ArmName(StrEnum):
    RAW = "raw"
    ENHANCED = "enhanced"


class ArmStatus(StrEnum):
    PLANNED = "planned"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    FAILED = "failed"


class CleanupPolicy(StrEnum):
    DELETE_BACKEND = "delete_backend"
    KEEP_BACKEND = "keep_backend"


class BackendArtifactState(StrEnum):
    RETAINED = "retained"
    DELETED = "deleted"


class ArmOrder(StrEnum):
    RAW_FIRST = "raw_first"
    ENHANCED_FIRST = "enhanced_first"


class MetricName(StrEnum):
    VQA_SCORE = "vqascore"
    IMAGE_REWARD = "image_reward"
    TIFA = "tifa"


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must contain non-whitespace text")
    return value


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value


def _relative_artifact_path(value: str) -> str:
    if not value.strip():
        raise ValueError("relative artifact path must not be empty")
    windows_path = PureWindowsPath(value)
    if (
        PurePosixPath(value).is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
    ):
        raise ValueError("must be a relative artifact path")
    normalized = value.replace("\\", "/")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError("relative artifact path must not contain '..'")
    return normalized


NonBlankText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=8192),
    AfterValidator(_non_blank),
]
Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
Sha256 = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]
GitSha = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{7,40}$"),
]
RelativeArtifactPath = Annotated[str, AfterValidator(_relative_artifact_path)]
AwareDateTime = Annotated[datetime, AfterValidator(_aware_datetime)]
class ArtifactModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


class BenchmarkCase(ArtifactModel):
    schema_version: Literal[1]
    case_id: Identifier
    source: NonBlankText
    language: BenchmarkLanguage
    category: BenchmarkCategory
    original_prompt: NonBlankText
    evaluation_prompt: NonBlankText
    evaluation_prompt_en: NonBlankText | None = None
    evaluation_prompt_en_reviewed: bool = False
    target_mode: Literal["t2i"]
    target_model: NonBlankText
    creativity_preset: CreativityPreset
    aspect_ratio: Annotated[
        str,
        StringConstraints(min_length=3, max_length=16, pattern=r"^[1-9][0-9]*:[1-9][0-9]*$"),
    ]
    samples_per_arm: int = Field(ge=1, le=4)
    enabled: bool

    @model_validator(mode="after")
    def validate_canonical_english_review(self) -> BenchmarkCase:
        if self.evaluation_prompt_en and not self.evaluation_prompt_en_reviewed:
            raise ValueError(
                "evaluation_prompt_en requires evaluation_prompt_en_reviewed=true"
            )
        if self.evaluation_prompt_en_reviewed and not self.evaluation_prompt_en:
            raise ValueError(
                "evaluation_prompt_en_reviewed=true requires evaluation_prompt_en"
            )
        return self


class FailureRecord(ArtifactModel):
    code: Identifier
    message: NonBlankText
    retry_count: int = Field(ge=0)
    retryable: bool


class AssetRecord(ArtifactModel):
    asset_id: Identifier
    job_id: Identifier
    sample_index: int = Field(ge=0)
    relative_path: RelativeArtifactPath
    sha256: Sha256
    media_type: Annotated[str, StringConstraints(pattern=r"^image/[A-Za-z0-9.+-]+$")]
    byte_size: int = Field(ge=1)


class ArmRecord(ArtifactModel):
    arm: ArmName
    status: ArmStatus
    request_order: int = Field(ge=0, le=1)
    execution_prompt: NonBlankText | None = None
    execution_prompt_sha256: Sha256 | None = None
    enhancement_id: Identifier | None = None
    job_id: Identifier | None = None
    target_model: NonBlankText
    aspect_ratio: Annotated[
        str,
        StringConstraints(min_length=3, max_length=16, pattern=r"^[1-9][0-9]*:[1-9][0-9]*$"),
    ]
    requested_samples: int = Field(ge=1, le=4)
    generation_parameters: dict[str, JsonValue] = Field(default_factory=dict)
    retry_count: int = Field(default=0, ge=0)
    assets: tuple[AssetRecord, ...] = ()
    failure: FailureRecord | None = None

    @model_validator(mode="after")
    def validate_arm_checkpoint(self) -> ArmRecord:
        if (self.execution_prompt is None) != (self.execution_prompt_sha256 is None):
            raise ValueError(
                "execution_prompt and execution_prompt_sha256 must be recorded together"
            )
        if self.execution_prompt is not None:
            expected = prompt_sha256(self.execution_prompt)
            if self.execution_prompt_sha256 != expected:
                raise ValueError(
                    "execution_prompt_sha256 does not match the exact execution_prompt"
                )
        if self.arm == ArmName.RAW and self.enhancement_id is not None:
            raise ValueError("raw arm must not contain enhancement_id")
        if self.status in {ArmStatus.SUBMITTED, ArmStatus.COMPLETED} and not self.job_id:
            raise ValueError(f"{self.status.value} arm requires job_id")
        if self.status in {ArmStatus.SUBMITTED, ArmStatus.COMPLETED}:
            if self.execution_prompt is None:
                raise ValueError(
                    f"{self.status.value} arm requires an execution prompt and hash"
                )
            if self.arm == ArmName.ENHANCED and self.enhancement_id is None:
                raise ValueError(
                    "submitted or completed enhanced arm requires enhancement_id"
                )
        if self.status == ArmStatus.COMPLETED:
            if len(self.assets) != self.requested_samples:
                raise ValueError(
                    "completed arm asset count must equal requested_samples"
                )
            if self.failure is not None:
                raise ValueError("completed arm must not contain failure")
        if self.status == ArmStatus.FAILED and self.failure is None:
            raise ValueError("failed arm requires failure metadata")
        if self.status != ArmStatus.FAILED and self.failure is not None:
            raise ValueError("only failed arms may contain failure metadata")
        sample_indexes = [asset.sample_index for asset in self.assets]
        if len(sample_indexes) != len(set(sample_indexes)):
            raise ValueError("asset sample_index values must be unique within an arm")
        if any(index >= self.requested_samples for index in sample_indexes):
            raise ValueError("asset sample_index must be lower than requested_samples")
        if self.job_id and any(asset.job_id != self.job_id for asset in self.assets):
            raise ValueError("asset job_id must match the arm job_id")
        if self.failure and self.failure.retry_count != self.retry_count:
            raise ValueError("failure retry_count must match the arm retry_count")
        return self


class PairRecord(ArtifactModel):
    schema_version: Literal[1]
    run_id: Identifier
    case_id: Identifier
    language: BenchmarkLanguage
    category: BenchmarkCategory
    evaluation_prompt_sha256: Sha256
    arm_order: ArmOrder
    raw: ArmRecord
    enhanced: ArmRecord

    @model_validator(mode="after")
    def validate_pair(self) -> PairRecord:
        if self.raw.arm != ArmName.RAW:
            raise ValueError("raw checkpoint must use arm='raw'")
        if self.enhanced.arm != ArmName.ENHANCED:
            raise ValueError("enhanced checkpoint must use arm='enhanced'")
        expected_orders = {
            ArmOrder.RAW_FIRST: (0, 1),
            ArmOrder.ENHANCED_FIRST: (1, 0),
        }
        raw_order, enhanced_order = expected_orders[self.arm_order]
        if (self.raw.request_order, self.enhanced.request_order) != (
            raw_order,
            enhanced_order,
        ):
            raise ValueError("request_order values do not match arm_order")
        return self


class JobCleanupRecord(ArtifactModel):
    job_id: Identifier
    case_id: Identifier
    arm: ArmName
    state: BackendArtifactState
    updated_at: AwareDateTime


class CleanupRecord(ArtifactModel):
    schema_version: Literal[1]
    run_id: Identifier
    policy: CleanupPolicy
    jobs: tuple[JobCleanupRecord, ...] = ()

    @model_validator(mode="after")
    def validate_unique_jobs(self) -> CleanupRecord:
        job_ids = [job.job_id for job in self.jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("cleanup jobs must not contain duplicate job_id values")
        return self


class EnhancerConfig(ArtifactModel):
    model: NonBlankText
    template_version: Identifier
    template_sha256: Sha256


class MetricAdapterConfig(ArtifactModel):
    metric: MetricName
    adapter: Identifier
    model_revision: NonBlankText
    evidence_kind: EvidenceKind
    settings: dict[str, JsonValue] = Field(default_factory=dict)


class StatisticsConfig(ArtifactModel):
    bootstrap_seed: int = Field(ge=0)
    bootstrap_resamples: int = Field(ge=1)
    tie_thresholds: dict[MetricName, float]

    @field_validator("tie_thresholds")
    @classmethod
    def validate_tie_thresholds(
        cls,
        value: dict[MetricName, float],
    ) -> dict[MetricName, float]:
        if {metric.value for metric in value} != ALL_METRICS:
            raise ValueError(
                "tie_thresholds must define vqascore, image_reward, and tifa"
            )
        if any(not math.isfinite(threshold) or threshold < 0 for threshold in value.values()):
            raise ValueError("tie thresholds must be finite and non-negative")
        return value


class RunManifest(ArtifactModel):
    schema_version: Literal[1]
    run_id: Identifier
    lifecycle: RunLifecycle
    started_at: AwareDateTime
    updated_at: AwareDateTime
    completed_at: AwareDateTime | None = None
    git_sha: GitSha
    dirty_worktree: bool
    provider_mode: ProviderMode
    evidence_kind: EvidenceKind
    benchmark_path: RelativeArtifactPath
    benchmark_sha256: Sha256
    enhancer: EnhancerConfig
    generation_models: tuple[NonBlankText, ...] = Field(min_length=1)
    metric_adapters: tuple[MetricAdapterConfig, ...] = Field(min_length=1)
    statistics: StatisticsConfig
    order_policy: Literal["alternating_by_case"]
    pairs: tuple[PairRecord, ...] = ()
    artifact_hashes: dict[RelativeArtifactPath, Sha256] = Field(default_factory=dict)
    last_error: FailureRecord | None = None

    @model_validator(mode="after")
    def validate_manifest(self) -> RunManifest:
        if self.updated_at < self.started_at:
            raise ValueError("updated_at must not be earlier than started_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not be earlier than started_at")
        if self.lifecycle == RunLifecycle.COMPLETED and self.completed_at is None:
            raise ValueError("completed manifest requires completed_at")
        if self.lifecycle != RunLifecycle.COMPLETED and self.completed_at is not None:
            raise ValueError("completed_at is only valid for completed manifests")
        if self.lifecycle == RunLifecycle.FAILED and self.last_error is None:
            raise ValueError("failed manifest requires last_error")
        if self.lifecycle != RunLifecycle.FAILED and self.last_error is not None:
            raise ValueError("last_error is only valid for failed manifests")
        if self.provider_mode == ProviderMode.MOCK and self.evidence_kind != EvidenceKind.SYNTHETIC:
            raise ValueError("mock provider runs must use synthetic evidence_kind")

        generation_models = list(self.generation_models)
        if len(generation_models) != len(set(generation_models)):
            raise ValueError("generation_models must not contain duplicates")

        metrics = [adapter.metric.value for adapter in self.metric_adapters]
        if len(metrics) != len(set(metrics)):
            raise ValueError("metric_adapters must not contain duplicate metrics")
        if set(metrics) != ALL_METRICS:
            raise ValueError(
                "metric_adapters must define vqascore, image_reward, and tifa"
            )
        if any(adapter.evidence_kind != self.evidence_kind for adapter in self.metric_adapters):
            raise ValueError(
                "metric adapter evidence_kind must match manifest evidence_kind"
            )

        case_ids = [pair.case_id for pair in self.pairs]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("pairs contain duplicate case_id checkpoints")
        for pair in self.pairs:
            if pair.run_id != self.run_id:
                raise ValueError("pair run_id must match manifest run_id")
            if pair.schema_version != self.schema_version:
                raise ValueError("pair schema_version must match manifest schema_version")
            for arm in (pair.raw, pair.enhanced):
                if arm.target_model not in generation_models:
                    raise ValueError(
                        f"arm target_model {arm.target_model!r} is not in generation_models"
                    )
        return self


class ScoreRecord(ArtifactModel):
    schema_version: Literal[1]
    run_id: Identifier
    case_id: Identifier
    arm: ArmName
    asset_sha256: Sha256
    evaluation_prompt_sha256: Sha256
    metric: MetricName
    score: float
    adapter: Identifier
    model_revision: NonBlankText
    evidence_kind: EvidenceKind

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value


class CaseMetricRecord(ArtifactModel):
    schema_version: Literal[1]
    run_id: Identifier
    case_id: Identifier
    language: BenchmarkLanguage
    category: BenchmarkCategory
    metric: MetricName
    raw_sample_count: int = Field(ge=1)
    enhanced_sample_count: int = Field(ge=1)
    raw_mean: float
    enhanced_mean: float
    delta: float
    tie_threshold: float = Field(ge=0)
    outcome: Literal["win", "tie", "loss"]

    @model_validator(mode="after")
    def validate_case_metric(self) -> CaseMetricRecord:
        values = (
            self.raw_mean,
            self.enhanced_mean,
            self.delta,
            self.tie_threshold,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("case metric values must be finite")
        expected_delta = self.enhanced_mean - self.raw_mean
        if not math.isclose(self.delta, expected_delta, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("delta must equal enhanced_mean - raw_mean")
        expected_outcome = (
            "win"
            if self.delta > self.tie_threshold
            else "loss"
            if self.delta < -self.tie_threshold
            else "tie"
        )
        if self.outcome != expected_outcome:
            raise ValueError("outcome does not match delta and tie_threshold")
        return self


class MetricAggregate(ArtifactModel):
    metric: MetricName
    case_count: int = Field(ge=0)
    missing_case_count: int = Field(ge=0)
    raw_mean: float
    enhanced_mean: float
    mean_delta: float
    median_delta: float
    ci95_low: float
    ci95_high: float
    wins: int = Field(ge=0)
    ties: int = Field(ge=0)
    losses: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_aggregate(self) -> MetricAggregate:
        values = (
            self.raw_mean,
            self.enhanced_mean,
            self.mean_delta,
            self.median_delta,
            self.ci95_low,
            self.ci95_high,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("aggregate metric values must be finite")
        if self.ci95_low > self.ci95_high:
            raise ValueError("ci95_low must not exceed ci95_high")
        if self.wins + self.ties + self.losses != self.case_count:
            raise ValueError("wins + ties + losses must equal case_count")
        return self


class SliceAggregate(ArtifactModel):
    dimension: Identifier
    value: NonBlankText
    metrics: tuple[MetricAggregate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_metrics(self) -> SliceAggregate:
        names = [metric.metric for metric in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("slice metrics must not contain duplicates")
        return self


class AggregateReport(ArtifactModel):
    schema_version: Literal[1]
    run_id: Identifier
    evidence_kind: EvidenceKind
    generated_at: AwareDateTime
    completed_case_count: int = Field(ge=0)
    failed_case_count: int = Field(ge=0)
    metrics: tuple[MetricAggregate, ...] = Field(min_length=1)
    slices: tuple[SliceAggregate, ...] = ()
    missing_cases: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> AggregateReport:
        metrics = [metric.metric for metric in self.metrics]
        if len(metrics) != len(set(metrics)):
            raise ValueError("report metrics must not contain duplicates")
        if len(self.missing_cases) != len(set(self.missing_cases)):
            raise ValueError("missing_cases must not contain duplicates")
        return self


ArtifactType = TypeVar("ArtifactType", bound=ArtifactModel)


def prompt_sha256(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ArtifactSchemaError(f"Unable to read evaluation artifact {path}: {exc}") from exc


def _parse_json_object(raw: str, *, path: Path, artifact_kind: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArtifactSchemaError(
            f"Invalid JSON for {artifact_kind} at {path}: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc
    if not isinstance(value, dict):
        raise ArtifactSchemaError(
            f"Invalid {artifact_kind} at {path}: expected a JSON object"
        )
    return value


def _require_current_version(
    value: dict[str, object],
    *,
    path: Path,
    artifact_kind: str,
) -> None:
    if "schema_version" not in value:
        raise ArtifactSchemaError(
            f"Invalid {artifact_kind} at {path}: missing required schema_version"
        )
    version = value["schema_version"]
    if type(version) is not int or version != CURRENT_SCHEMA_VERSION:
        raise ArtifactSchemaError(
            f"Unsupported {artifact_kind} schema_version {version!r} at {path}; "
            f"supported version is {CURRENT_SCHEMA_VERSION}"
        )


def _validate_json_model(
    raw: str,
    model_type: type[ArtifactType],
    *,
    path: Path,
    artifact_kind: str,
) -> ArtifactType:
    value = _parse_json_object(raw, path=path, artifact_kind=artifact_kind)
    _require_current_version(value, path=path, artifact_kind=artifact_kind)
    try:
        return model_type.model_validate_json(raw)
    except ValidationError as exc:
        raise ArtifactSchemaError(
            f"Invalid {artifact_kind} at {path}: {exc}"
        ) from exc


def _load_jsonl(
    path: Path | str,
    model_type: type[ArtifactType],
    *,
    artifact_kind: str,
) -> list[ArtifactType]:
    artifact_path = Path(path)
    records: list[ArtifactType] = []
    for line_number, line in enumerate(_read_text(artifact_path).splitlines(), start=1):
        if not line.strip():
            continue
        record_path = Path(f"{artifact_path}:{line_number}")
        records.append(
            _validate_json_model(
                line,
                model_type,
                path=record_path,
                artifact_kind=artifact_kind,
            )
        )
    if not records:
        raise ArtifactSchemaError(f"{artifact_kind} file {artifact_path} contains no records")
    return records


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
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
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_jsonl(
    path: Path | str,
    records: list[ArtifactType] | tuple[ArtifactType, ...],
    model_type: type[ArtifactType],
    *,
    artifact_kind: str,
) -> None:
    if not records:
        raise ArtifactSchemaError(f"Cannot write empty {artifact_kind} records")
    validated = [model_type.model_validate(record.model_dump()) for record in records]
    content = "\n".join(record.model_dump_json() for record in validated) + "\n"
    _atomic_write(Path(path), content)


def load_benchmark_cases(path: Path | str) -> list[BenchmarkCase]:
    cases = _load_jsonl(path, BenchmarkCase, artifact_kind="benchmark case")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ArtifactSchemaError(f"Benchmark {path} contains duplicate case_id values")
    return cases


def write_benchmark_cases(path: Path | str, cases: list[BenchmarkCase]) -> None:
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ArtifactSchemaError("Cannot write benchmark with duplicate case_id values")
    _write_jsonl(path, cases, BenchmarkCase, artifact_kind="benchmark case")


def load_run_manifest(path: Path | str) -> RunManifest:
    artifact_path = Path(path)
    return _validate_json_model(
        _read_text(artifact_path),
        RunManifest,
        path=artifact_path,
        artifact_kind="run manifest",
    )


def write_run_manifest(path: Path | str, manifest: RunManifest) -> None:
    validated = RunManifest.model_validate(manifest.model_dump())
    _atomic_write(Path(path), validated.model_dump_json(indent=2) + "\n")


def load_cleanup_record(path: Path | str) -> CleanupRecord:
    artifact_path = Path(path)
    return _validate_json_model(
        _read_text(artifact_path),
        CleanupRecord,
        path=artifact_path,
        artifact_kind="cleanup record",
    )


def write_cleanup_record(path: Path | str, cleanup: CleanupRecord) -> None:
    validated = CleanupRecord.model_validate(cleanup.model_dump())
    _atomic_write(Path(path), validated.model_dump_json(indent=2) + "\n")


def load_pair_records(path: Path | str) -> list[PairRecord]:
    pairs = _load_jsonl(path, PairRecord, artifact_kind="pair record")
    case_ids = [pair.case_id for pair in pairs]
    if len(case_ids) != len(set(case_ids)):
        raise ArtifactSchemaError(f"Pair artifact {path} contains duplicate case_id values")
    return pairs


def write_pair_records(path: Path | str, pairs: list[PairRecord]) -> None:
    case_ids = [pair.case_id for pair in pairs]
    if len(case_ids) != len(set(case_ids)):
        raise ArtifactSchemaError("Cannot write pair records with duplicate case_id values")
    _write_jsonl(path, pairs, PairRecord, artifact_kind="pair record")


def load_score_records(path: Path | str) -> list[ScoreRecord]:
    return _load_jsonl(path, ScoreRecord, artifact_kind="score record")


def write_score_records(path: Path | str, scores: list[ScoreRecord]) -> None:
    _write_jsonl(path, scores, ScoreRecord, artifact_kind="score record")


def load_case_metric_records(path: Path | str) -> list[CaseMetricRecord]:
    records = _load_jsonl(
        path,
        CaseMetricRecord,
        artifact_kind="case metric record",
    )
    keys = [(record.case_id, record.metric) for record in records]
    if len(keys) != len(set(keys)):
        raise ArtifactSchemaError(
            f"Case metric artifact {path} contains duplicate case/metric values"
        )
    return records


def write_case_metric_records(
    path: Path | str,
    records: list[CaseMetricRecord],
) -> None:
    keys = [(record.case_id, record.metric) for record in records]
    if len(keys) != len(set(keys)):
        raise ArtifactSchemaError(
            "Cannot write case metric records with duplicate case/metric values"
        )
    _write_jsonl(
        path,
        records,
        CaseMetricRecord,
        artifact_kind="case metric record",
    )


def load_summary(path: Path | str) -> AggregateReport:
    artifact_path = Path(path)
    return _validate_json_model(
        _read_text(artifact_path),
        AggregateReport,
        path=artifact_path,
        artifact_kind="aggregate report",
    )


def write_summary(path: Path | str, report: AggregateReport) -> None:
    validated = AggregateReport.model_validate(report.model_dump())
    _atomic_write(Path(path), validated.model_dump_json(indent=2) + "\n")


def write_report_markdown(path: Path | str, content: str) -> None:
    if not content.strip():
        raise ArtifactSchemaError("Cannot write an empty Markdown report")
    _atomic_write(Path(path), content.rstrip() + "\n")
