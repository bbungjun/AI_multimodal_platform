from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from offline.offline_scorers import load_scorer_profile, validate_evaluation_inputs
from schemas import (
    AggregateReport,
    ArtifactModel,
    BenchmarkCategory,
    BenchmarkLanguage,
    CreativityPreset,
    EvidenceKind,
    MetricName,
    Sha256,
    file_sha256,
    load_benchmark_cases,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_POLICY_PATH = PACKAGE_ROOT / "pilot_policy.v1.json"
DEFAULT_PREFLIGHT_PATH = PACKAGE_ROOT / "runs" / "vertex-pilot-preflight-v1.json"


class PilotPolicyError(RuntimeError):
    """Raised when the paid pilot contract is incomplete or unsafe."""


class PilotModels(ArtifactModel):
    enhancer: str
    generator: str
    creativity_preset: CreativityPreset
    aspect_ratio: str


class PilotLimits(ArtifactModel):
    max_cases: int = Field(gt=0)
    max_enhancement_http_requests: int = Field(gt=0)
    max_generation_http_requests: int = Field(gt=0)
    max_generated_images: int = Field(gt=0)
    samples_per_arm: int = Field(ge=1, le=4)
    max_provider_retry_attempts: int = Field(ge=1)
    max_enhancement_call_groups_per_case: int = Field(ge=1)
    max_gemini_input_tokens_per_call: int = Field(gt=0)
    max_gemini_output_tokens_per_call: int = Field(gt=0)


class PilotBudget(ArtifactModel):
    approved_usd: Decimal = Field(gt=0)
    stop_at_usd: Decimal = Field(gt=0)
    pricing_as_of: date
    pricing_source_url: str
    imagen_fast_per_image_usd: Decimal = Field(gt=0)
    gemini_flash_input_per_million_tokens_usd: Decimal = Field(gt=0)
    gemini_flash_output_per_million_tokens_usd: Decimal = Field(gt=0)
    scope: Literal["workload_local_conservative_estimate"]
    limitation: str

    @model_validator(mode="after")
    def validate_cap(self) -> PilotBudget:
        if self.stop_at_usd > self.approved_usd:
            raise ValueError("stop_at_usd must not exceed approved_usd")
        return self


class PilotStatistics(ArtifactModel):
    bootstrap_seed: int = Field(ge=0)
    bootstrap_resamples: int = Field(ge=1000)
    tie_thresholds: dict[MetricName, float]

    @model_validator(mode="after")
    def validate_metrics(self) -> PilotStatistics:
        if set(self.tie_thresholds) != set(MetricName):
            raise ValueError("tie_thresholds must define all three metrics")
        if any(
            not math.isfinite(value) or value < 0
            for value in self.tie_thresholds.values()
        ):
            raise ValueError("tie_thresholds must be finite and non-negative")
        return self


class PilotDecisionPolicy(ArtifactModel):
    required_completed_cases: int = Field(gt=0)
    tifa_noninferiority_margin: float = Field(gt=0, lt=1)
    proceed_rule: str
    stop_rule: str
    otherwise: Literal["revise_or_expand"]
    slice_interpretation: str


class PilotApproval(ArtifactModel):
    budget_cap_approved: bool
    approved_budget_usd: Decimal = Field(gt=0)
    requires_post_mock_dry_run_execution_approval: bool
    provider_execution_approved: bool


class PilotPolicyModel(ArtifactModel):
    schema_version: Literal[1]
    policy_id: str
    benchmark_path: str
    benchmark_sha256: Sha256
    scorer_profile_path: str
    scorer_profile_sha256: Sha256
    models: PilotModels
    limits: PilotLimits
    budget: PilotBudget
    statistics: PilotStatistics
    decision: PilotDecisionPolicy
    approval: PilotApproval

    @model_validator(mode="after")
    def validate_approval(self) -> PilotPolicyModel:
        if not self.approval.budget_cap_approved:
            raise ValueError("pilot budget cap must be explicitly approved")
        if self.approval.approved_budget_usd != self.budget.approved_usd:
            raise ValueError("approval budget must match budget.approved_usd")
        if not self.approval.requires_post_mock_dry_run_execution_approval:
            raise ValueError("post-mock provider execution approval must be required")
        if self.approval.provider_execution_approved:
            raise ValueError(
                "provider execution approval is runtime evidence and must not be committed"
            )
        return self


@dataclass(frozen=True)
class LoadedPilotPolicy:
    path: Path
    model: PilotPolicyModel
    benchmark_path: Path
    scorer_profile_path: Path

    @property
    def sha256(self) -> str:
        return file_sha256(self.path)


def load_pilot_policy(path: Path | str = DEFAULT_POLICY_PATH) -> LoadedPilotPolicy:
    policy_path = Path(path).resolve()
    try:
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
        model = PilotPolicyModel.model_validate(raw)
    except (OSError, ValueError) as exc:
        raise PilotPolicyError(f"Cannot load pilot policy {policy_path}: {exc}") from exc

    benchmark_path = _relative_input(policy_path, model.benchmark_path)
    profile_path = _relative_input(policy_path, model.scorer_profile_path)
    for label, input_path, expected_hash in (
        ("benchmark", benchmark_path, model.benchmark_sha256),
        ("scorer profile", profile_path, model.scorer_profile_sha256),
    ):
        if not input_path.is_file():
            raise PilotPolicyError(f"Pinned {label} is missing: {input_path.name}")
        if file_sha256(input_path) != expected_hash:
            raise PilotPolicyError(f"Pinned {label} hash does not match pilot policy")

    loaded = LoadedPilotPolicy(policy_path, model, benchmark_path, profile_path)
    validate_pilot_inputs(loaded)
    return loaded


def _relative_input(policy_path: Path, value: str) -> Path:
    root = policy_path.parent.resolve()
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PilotPolicyError(f"Pilot input escaped policy directory: {value}") from exc
    return resolved


def validate_pilot_inputs(policy: LoadedPilotPolicy) -> None:
    model = policy.model
    if model.decision.required_completed_cases != model.limits.max_cases:
        raise PilotPolicyError("Decision completeness count must match the case cap")
    all_cases = load_benchmark_cases(policy.benchmark_path)
    cases = [case for case in all_cases if case.enabled]
    if len(all_cases) != model.limits.max_cases or len(cases) != model.limits.max_cases:
        raise PilotPolicyError("Pilot benchmark must contain exactly 20 enabled cases")

    language_counts = Counter(case.language for case in cases)
    expected_languages = {
        BenchmarkLanguage.ENGLISH: 10,
        BenchmarkLanguage.KOREAN: 10,
    }
    if language_counts != expected_languages:
        raise PilotPolicyError("Pilot benchmark must contain 10 English and 10 Korean cases")

    category_counts = Counter(case.category for case in cases)
    if category_counts != Counter({category: 4 for category in BenchmarkCategory}):
        raise PilotPolicyError("Each pilot category must contain exactly four cases")
    cross_counts = Counter((case.language, case.category) for case in cases)
    expected_cross = Counter(
        {
            (language, category): 2
            for language in BenchmarkLanguage
            for category in BenchmarkCategory
        }
    )
    if cross_counts != expected_cross:
        raise PilotPolicyError(
            "Each language/category pilot slice must contain exactly two cases"
        )

    for case in cases:
        if (
            case.target_model != model.models.generator
            or case.creativity_preset != model.models.creativity_preset
            or case.aspect_ratio != model.models.aspect_ratio
            or case.samples_per_arm != model.limits.samples_per_arm
        ):
            raise PilotPolicyError(
                f"Case {case.case_id} does not match the pinned model parameters"
            )

    expected_enhancements = len(cases)
    expected_generation_requests = len(cases) * 2
    expected_images = expected_generation_requests * model.limits.samples_per_arm
    if expected_enhancements != model.limits.max_enhancement_http_requests:
        raise PilotPolicyError("Enhancement request limit does not match benchmark size")
    if expected_generation_requests != model.limits.max_generation_http_requests:
        raise PilotPolicyError("Generation request limit does not match paired arms")
    if expected_images != model.limits.max_generated_images:
        raise PilotPolicyError("Image limit does not match cases, arms, and samples")

    scorer_profile = load_scorer_profile(policy.scorer_profile_path)
    inputs = validate_evaluation_inputs(scorer_profile, policy.benchmark_path)
    if {case.case_id for case in inputs.cases} != {case.case_id for case in cases}:
        raise PilotPolicyError("Scorer profile does not cover the exact pilot benchmark")
    calibrated = scorer_profile.data["calibration"]["minimum_floors"]
    for metric, threshold in model.statistics.tie_thresholds.items():
        if float(calibrated[metric.value]) != threshold:
            raise PilotPolicyError(
                f"Pilot tie threshold for {metric.value} differs from scorer calibration"
            )


def build_preflight(policy: LoadedPilotPolicy) -> dict[str, object]:
    model = policy.model
    limits = model.limits
    budget = model.budget
    per_gemini_call = (
        Decimal(limits.max_gemini_input_tokens_per_call)
        * budget.gemini_flash_input_per_million_tokens_usd
        / Decimal(1_000_000)
        + Decimal(limits.max_gemini_output_tokens_per_call)
        * budget.gemini_flash_output_per_million_tokens_usd
        / Decimal(1_000_000)
    )
    normal_imagen = (
        Decimal(limits.max_generated_images) * budget.imagen_fast_per_image_usd
    )
    normal_gemini = (
        Decimal(limits.max_enhancement_http_requests) * per_gemini_call
    )
    retry_imagen = normal_imagen * Decimal(limits.max_provider_retry_attempts)
    retry_gemini = (
        normal_gemini
        * Decimal(limits.max_enhancement_call_groups_per_case)
        * Decimal(limits.max_provider_retry_attempts)
    )
    normal_total = normal_imagen + normal_gemini
    retry_total = retry_imagen + retry_gemini
    if retry_total > budget.stop_at_usd:
        raise PilotPolicyError(
            f"Conservative retry envelope ${retry_total} exceeds budget stop "
            f"${budget.stop_at_usd}"
        )
    git = _git_provenance()
    return {
        "schema_version": 1,
        "plan_id": model.policy_id,
        "provider_calls": "none",
        "policy_path": policy.path.name,
        "policy_sha256": policy.sha256,
        "benchmark_path": model.benchmark_path,
        "benchmark_sha256": model.benchmark_sha256,
        "scorer_profile_path": model.scorer_profile_path,
        "scorer_profile_sha256": model.scorer_profile_sha256,
        "implementation": git,
        "models": model.models.model_dump(mode="json"),
        "limits": model.limits.model_dump(mode="json"),
        "budget": {
            "approved_usd": _money(budget.approved_usd),
            "stop_at_usd": _money(budget.stop_at_usd),
            "normal_estimate_usd": _money(normal_total),
            "conservative_retry_envelope_usd": _money(retry_total),
            "headroom_after_retry_envelope_usd": _money(
                budget.stop_at_usd - retry_total
            ),
            "normal_imagen_usd": _money(normal_imagen),
            "normal_gemini_envelope_usd": _money(normal_gemini),
            "retry_imagen_envelope_usd": _money(retry_imagen),
            "retry_gemini_envelope_usd": _money(retry_gemini),
            "pricing_as_of": budget.pricing_as_of.isoformat(),
            "pricing_source_url": budget.pricing_source_url,
            "scope": budget.scope,
            "limitation": budget.limitation,
        },
        "statistics": model.statistics.model_dump(mode="json"),
        "decision": model.decision.model_dump(mode="json"),
        "approval": {
            "budget_cap_approved": model.approval.budget_cap_approved,
            "provider_execution_approved": False,
            "requires_post_mock_dry_run_execution_approval": True,
            "approvable_clean_revision": not git["dirty_worktree"],
        },
    }


def _git_provenance() -> dict[str, object]:
    values: dict[str, str] = {}
    for name, arguments in (
        ("commit_sha", ["git", "rev-parse", "HEAD"]),
        ("tree_sha", ["git", "rev-parse", "HEAD^{tree}"]),
    ):
        result = subprocess.run(
            arguments,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        value = result.stdout.strip()
        if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", value):
            raise PilotPolicyError(f"Cannot determine Git {name}")
        values[name] = value
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        raise PilotPolicyError("Cannot determine Git worktree status")
    return {**values, "dirty_worktree": bool(status.stdout.strip())}


def decide_pilot(
    report: AggregateReport,
    policy: LoadedPilotPolicy,
) -> dict[str, object]:
    decision = policy.model.decision
    metrics = {metric.metric: metric for metric in report.metrics}
    if set(metrics) != set(MetricName):
        raise PilotPolicyError("Pilot report must contain all three metrics")
    if report.evidence_kind != EvidenceKind.REAL:
        raise PilotPolicyError("Pilot decision requires real scorer evidence")

    incomplete = (
        report.completed_case_count != decision.required_completed_cases
        or report.failed_case_count > 0
        or bool(report.missing_cases)
    )
    vqa = metrics[MetricName.VQA_SCORE]
    reward = metrics[MetricName.IMAGE_REWARD]
    tifa = metrics[MetricName.TIFA]
    margin = decision.tifa_noninferiority_margin
    proceed = (
        not incomplete
        and vqa.mean_delta > 0
        and reward.mean_delta > 0
        and (vqa.ci95_low > 0 or reward.ci95_low > 0)
        and vqa.ci95_high >= 0
        and reward.ci95_high >= 0
        and tifa.ci95_low >= -margin
    )
    stop = (
        (vqa.ci95_high < 0 and reward.ci95_high < 0)
        or tifa.ci95_high < -margin
    )
    recommendation = (
        "proceed_to_full_benchmark_review"
        if proceed
        else "stop"
        if stop
        else "revise_or_expand"
    )
    return {
        "schema_version": 1,
        "run_id": report.run_id,
        "policy_id": policy.model.policy_id,
        "policy_sha256": policy.sha256,
        "recommendation": recommendation,
        "all_cases_complete": not incomplete,
        "tifa_noninferiority_margin": margin,
        "observed": {
            metric.value: {
                "mean_delta": metrics[metric].mean_delta,
                "ci95_low": metrics[metric].ci95_low,
                "ci95_high": metrics[metric].ci95_high,
            }
            for metric in MetricName
        },
        "rules": {
            "proceed": decision.proceed_rule,
            "stop": decision.stop_rule,
            "otherwise": decision.otherwise,
        },
    }


def write_preflight(path: Path | str, value: dict[str, object]) -> Path:
    destination = Path(path).resolve()
    runs_root = (PACKAGE_ROOT / "runs").resolve()
    if destination != runs_root and runs_root not in destination.parents:
        raise PilotPolicyError("Preflight output must be under the ignored runs directory")
    _atomic_json_write(destination, value)
    return destination


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _atomic_json_write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the $20 Vertex pilot contract without provider calls."
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_PREFLIGHT_PATH)
    arguments = parser.parse_args(argv)
    try:
        policy = load_pilot_policy(arguments.policy)
        preflight = build_preflight(policy)
        output = write_preflight(arguments.output, preflight)
    except PilotPolicyError as exc:
        print(f"VERTEX PILOT PREFLIGHT FAILED: {exc}")
        return 1
    state = (
        "READY"
        if preflight["approval"]["approvable_clean_revision"]
        else "CANDIDATE ONLY — DIRTY WORKTREE"
    )
    print(
        f"VERTEX PILOT PREFLIGHT {state} — NO PROVIDER CALLS. "
        f"plan_sha256={file_sha256(output)} "
        f"normal_usd={preflight['budget']['normal_estimate_usd']} "
        f"retry_envelope_usd={preflight['budget']['conservative_retry_envelope_usd']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
