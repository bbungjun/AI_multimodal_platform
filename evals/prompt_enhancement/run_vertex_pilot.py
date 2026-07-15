from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from generate_pairs import (
    DEFAULT_RUNS_DIR,
    EvaluationClient,
    EvaluationRunnerError,
    HttpClient,
    HttpRequestError,
    RunnerConfig,
    run_pairs,
)
from offline.offline_scorers import load_scorer_profile, metric_adapter_configs
from pilot import (
    DEFAULT_POLICY_PATH,
    LoadedPilotPolicy,
    PilotPolicyError,
    build_preflight,
    load_pilot_policy,
)
from schemas import (
    ArtifactModel,
    EvidenceKind,
    FailureRecord,
    MetricName,
    ProviderMode,
    RunLifecycle,
    StatisticsConfig,
    file_sha256,
    load_run_manifest,
    load_summary,
    write_run_manifest,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class VertexPilotError(RuntimeError):
    """Raised before or during a budget-guarded Vertex pilot."""


class UsageEvent(ArtifactModel):
    sequence: int
    kind: Literal["enhancement", "generation"]
    step_name: str
    status: Literal["reserved", "succeeded", "failed"]
    requested_at: datetime
    completed_at: datetime | None = None
    model: str
    requested_images: int = 0
    response_id: str | None = None
    http_latency_ms: int | None = None
    provider_latency_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    provider_attempts: int | None = None
    vertex_charged: bool | None = None
    job_state: str | None = None
    job_latency_ms: int | None = None
    http_status: int | None = None
    provider_failure_code: str | None = None
    failure_reason: str | None = None
    failure_field: str | None = None
    failure_source: str | None = None
    failure_type: str | None = None


class UsageLedger(ArtifactModel):
    schema_version: Literal[1]
    run_id: str
    policy_id: str
    policy_sha256: str
    approved_plan_sha256: str
    events: tuple[UsageEvent, ...] = ()


class BudgetedVertexClient:
    def __init__(
        self,
        wrapped: EvaluationClient,
        *,
        policy: LoadedPilotPolicy,
        run_id: str,
        ledger_path: Path,
        approved_plan_sha256: str,
    ) -> None:
        self.wrapped = wrapped
        self.policy = policy
        self.ledger_path = ledger_path
        self.approved_plan_sha256 = approved_plan_sha256
        if ledger_path.is_file():
            try:
                self.ledger = UsageLedger.model_validate_json(
                    ledger_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise VertexPilotError(f"Cannot load usage ledger: {exc}") from exc
            if (
                self.ledger.run_id != run_id
                or self.ledger.policy_sha256 != policy.sha256
                or self.ledger.approved_plan_sha256 != approved_plan_sha256
            ):
                raise VertexPilotError("Usage ledger does not match this approved pilot")
        else:
            self.ledger = UsageLedger(
                schema_version=1,
                run_id=run_id,
                policy_id=policy.model.policy_id,
                policy_sha256=policy.sha256,
                approved_plan_sha256=approved_plan_sha256,
                events=(),
            )

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
        event_index: int | None = None
        if method == "POST" and path in {"/api/prompts/enhance", "/api/generations"}:
            event_index = self._reserve(path, step_name, payload or {})
        started = time.monotonic()
        try:
            response = self.wrapped.request_json(
                method,
                path,
                expected_status=expected_status,
                step_name=step_name,
                payload=payload,
                headers=headers,
            )
        except Exception as exc:
            if event_index is not None:
                failure_metadata = _http_failure_metadata(exc)
                self._finish(
                    event_index,
                    status="failed",
                    http_latency_ms=_elapsed_ms(started),
                    failure_type=type(exc).__name__,
                    **failure_metadata,
                )
            raise
        if event_index is not None:
            self._finish_success(event_index, response, _elapsed_ms(started))
        elif method == "GET" and path.startswith("/api/generations/"):
            self._update_generation_status(response)
        return response

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
        return self.wrapped.request_bytes(
            method,
            path,
            expected_status=expected_status,
            step_name=step_name,
            payload=payload,
            headers=headers,
        )

    def _reserve(self, path: str, step_name: str, payload: Mapping[str, Any]) -> int:
        if any(event.step_name == step_name for event in self.ledger.events):
            raise VertexPilotError(
                f"Usage ledger already contains {step_name!r}; reconcile the manifest "
                "before another billable request."
            )
        model = self.policy.model
        kind = "enhancement" if path == "/api/prompts/enhance" else "generation"
        requested_images = 0
        request_model = (
            model.models.enhancer if kind == "enhancement" else str(payload.get("model", ""))
        )
        if kind == "generation":
            requested_images = int(payload.get("number_of_images", 0))
            if request_model != model.models.generator:
                raise VertexPilotError("Generation model differs from the approved policy")
            if requested_images != model.limits.samples_per_arm:
                raise VertexPilotError("Generation sample count differs from approved policy")

        events = list(self.ledger.events)
        enhancement_count = sum(event.kind == "enhancement" for event in events)
        generation_count = sum(event.kind == "generation" for event in events)
        image_count = sum(event.requested_images for event in events)
        if kind == "enhancement":
            enhancement_count += 1
        else:
            generation_count += 1
            image_count += requested_images
        limits = model.limits
        if enhancement_count > limits.max_enhancement_http_requests:
            raise VertexPilotError("Enhancement HTTP request hard cap reached")
        if generation_count > limits.max_generation_http_requests:
            raise VertexPilotError("Generation HTTP request hard cap reached")
        if image_count > limits.max_generated_images:
            raise VertexPilotError("Generated-image hard cap reached")

        candidate = UsageEvent(
            sequence=len(events) + 1,
            kind=kind,
            step_name=step_name,
            status="reserved",
            requested_at=_utc_now(),
            model=request_model,
            requested_images=requested_images,
        )
        events.append(candidate)
        if _conservative_committed_cost(events, self.policy) > model.budget.stop_at_usd:
            raise VertexPilotError("$20 workload-local budget hard cap reached")
        self._replace_events(events)
        return len(events) - 1

    def _finish_success(
        self,
        event_index: int,
        response: Mapping[str, Any],
        latency_ms: int,
    ) -> None:
        event = self.ledger.events[event_index]
        changes: dict[str, Any] = {
            "status": "succeeded",
            "completed_at": _utc_now(),
            "response_id": _string_or_none(response.get("id")),
            "http_latency_ms": latency_ms,
        }
        if event.kind == "enhancement":
            changes.update(
                {
                    "provider_latency_ms": _nonnegative_int(response.get("latency_ms")),
                    "tokens_in": _nonnegative_int(response.get("tokens_in")),
                    "tokens_out": _nonnegative_int(response.get("tokens_out")),
                }
            )
        else:
            changes.update(
                {
                    "provider_attempts": _nonnegative_int(response.get("attempts")),
                    "vertex_charged": _bool_or_none(response.get("vertex_charged")),
                }
            )
        self._update_event(event_index, changes)

    def _finish(self, event_index: int, **changes: Any) -> None:
        changes.setdefault("completed_at", _utc_now())
        self._update_event(event_index, changes)

    def _update_generation_status(self, response: Mapping[str, Any]) -> None:
        response_id = _string_or_none(response.get("id"))
        if response_id is None:
            return
        for index, event in enumerate(self.ledger.events):
            if event.kind == "generation" and event.response_id == response_id:
                attempts = _nonnegative_int(response.get("attempts"))
                if (
                    attempts is not None
                    and attempts > self.policy.model.limits.max_provider_retry_attempts
                ):
                    raise VertexPilotError(
                        "Backend provider attempts exceeded the approved retry cap"
                    )
                job_state = _string_or_none(response.get("state"))
                changes = {
                    "provider_attempts": attempts,
                    "vertex_charged": _bool_or_none(response.get("vertex_charged")),
                    "job_state": job_state,
                }
                if job_state in {"completed", "failed", "cancelled"}:
                    completed_at = _utc_now()
                    changes["completed_at"] = completed_at
                    changes["job_latency_ms"] = max(
                        0,
                        round((completed_at - event.requested_at).total_seconds() * 1000),
                    )
                    error = response.get("error")
                    if isinstance(error, Mapping):
                        changes["provider_failure_code"] = _string_or_none(
                            error.get("code")
                        )
                if any(getattr(event, key) != value for key, value in changes.items()):
                    self._update_event(index, changes)
                return

    def _update_event(self, index: int, changes: Mapping[str, Any]) -> None:
        events = list(self.ledger.events)
        events[index] = UsageEvent.model_validate(
            events[index].model_copy(update=dict(changes)).model_dump()
        )
        self._replace_events(events)

    def _replace_events(self, events: list[UsageEvent]) -> None:
        self.ledger = UsageLedger.model_validate(
            self.ledger.model_copy(update={"events": tuple(events)}).model_dump()
        )
        _atomic_json_write(
            self.ledger_path,
            self.ledger.model_dump(mode="json"),
        )


def run_vertex_pilot(
    *,
    policy_path: Path,
    preflight_path: Path,
    approved_plan_sha256: str,
    mock_run_dir: Path,
    base_url: str,
    runs_dir: Path,
    run_id: str,
    keep_artifacts: bool,
    poll_timeout_sec: float,
    poll_interval_sec: float,
    health_timeout_sec: float,
    environ: Mapping[str, str],
    client: EvaluationClient | None = None,
) -> Any:
    policy = load_pilot_policy(policy_path)
    _require_execution_approval(environ, policy, approved_plan_sha256)
    _verify_preflight(preflight_path, policy, approved_plan_sha256)
    git_sha, dirty = _git_metadata()
    if dirty:
        raise VertexPilotError("Vertex pilot requires a clean worktree")
    _verify_mock_dry_run(mock_run_dir, policy, expected_git_sha=git_sha)

    profile = load_scorer_profile(policy.scorer_profile_path)
    statistics = StatisticsConfig(
        bootstrap_seed=policy.model.statistics.bootstrap_seed,
        bootstrap_resamples=policy.model.statistics.bootstrap_resamples,
        tie_thresholds=policy.model.statistics.tie_thresholds,
    )
    config = RunnerConfig(
        base_url=base_url,
        benchmark_path=policy.benchmark_path,
        runs_dir=runs_dir,
        run_id=run_id,
        keep_artifacts=keep_artifacts,
        poll_timeout_sec=poll_timeout_sec,
        poll_interval_sec=poll_interval_sec,
        expected_enhancer_model=policy.model.models.enhancer,
        expected_template_version="v1",
        git_sha=git_sha,
        dirty_worktree=False,
        health_timeout_sec=health_timeout_sec,
        provider_mode=ProviderMode.VERTEX,
        evidence_kind=EvidenceKind.REAL,
        metric_adapters=tuple(metric_adapter_configs(profile)),
        statistics=statistics,
        expected_provider_retry_max_attempts=(
            policy.model.limits.max_provider_retry_attempts
        ),
    )
    run_dir = runs_dir / run_id
    budgeted_client = BudgetedVertexClient(
        client or HttpClient(base_url),
        policy=policy,
        run_id=run_id,
        ledger_path=run_dir / "pilot_usage.json",
        approved_plan_sha256=approved_plan_sha256,
    )
    try:
        manifest = run_pairs(config, client=budgeted_client, environ=environ)
    except (EvaluationRunnerError, VertexPilotError) as exc:
        _write_usage_summary(run_dir, budgeted_client.ledger, policy)
        _persist_vertex_failure(run_dir, exc)
        raise
    _write_usage_summary(run_dir, budgeted_client.ledger, policy)
    return manifest


def _http_failure_metadata(exc: Exception) -> dict[str, Any]:
    if not isinstance(exc, HttpRequestError):
        return {}
    return {
        "http_status": exc.status_code,
        "provider_failure_code": exc.public_error_code,
        "failure_reason": exc.public_error_reason,
        "failure_field": exc.public_error_field,
        "failure_source": exc.public_error_source,
    }


def _persist_vertex_failure(run_dir: Path, exc: Exception) -> None:
    """Close an existing real-run manifest without persisting raw API text."""

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = load_run_manifest(manifest_path)
    except (OSError, ValueError) as manifest_error:
        raise VertexPilotError(
            "Vertex pilot failed and its manifest could not be loaded for failure persistence"
        ) from manifest_error

    public_code = (
        exc.public_error_code
        if isinstance(exc, HttpRequestError) and exc.public_error_code
        else "vertex_pilot_request_failed"
    )
    message = (
        "Prompt enhancement response failed validation."
        if public_code == "prompt_enhancement_invalid_response"
        else "Vertex pilot request failed; inspect prompt-free usage metadata."
    )
    failed = manifest.model_copy(
        update={
            "lifecycle": RunLifecycle.FAILED,
            "updated_at": _utc_now(),
            "completed_at": None,
            "last_error": FailureRecord(
                code=public_code,
                message=message,
                retry_count=0,
                retryable=False,
            ),
        }
    )
    write_run_manifest(manifest_path, failed)


def _require_execution_approval(
    environ: Mapping[str, str],
    policy: LoadedPilotPolicy,
    approved_plan_sha256: str,
) -> None:
    expected = {
        "AI_PROVIDER": "vertex",
        "VERTEX_PILOT_EXECUTION_APPROVED": "yes",
        "VERTEX_PILOT_GCP_GUARD": "passed",
        "VERTEX_PILOT_APPROVED_PLAN_SHA256": approved_plan_sha256,
        "PROVIDER_RETRY_MAX_ATTEMPTS": str(
            policy.model.limits.max_provider_retry_attempts
        ),
    }
    missing = [key for key, value in expected.items() if environ.get(key) != value]
    if missing:
        raise VertexPilotError(
            "Vertex pilot execution guard failed for: " + ", ".join(sorted(missing))
        )
    if not re.fullmatch(r"[0-9a-f]{64}", approved_plan_sha256):
        raise VertexPilotError("Approved plan SHA-256 is invalid")


def _verify_preflight(
    path: Path,
    policy: LoadedPilotPolicy,
    approved_plan_sha256: str,
) -> None:
    if not path.is_file() or file_sha256(path) != approved_plan_sha256:
        raise VertexPilotError("Approved preflight file hash does not match")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VertexPilotError(f"Cannot load approved preflight: {exc}") from exc
    expected = build_preflight(policy)
    if value != expected:
        raise VertexPilotError("Approved preflight content differs from current policy")
    approval = value.get("approval")
    if not isinstance(approval, dict) or approval.get("approvable_clean_revision") is not True:
        raise VertexPilotError("Approved preflight was not created from a clean revision")


def _verify_mock_dry_run(
    path: Path,
    policy: LoadedPilotPolicy,
    *,
    expected_git_sha: str,
) -> None:
    manifest = load_run_manifest(path / "manifest.json")
    report = load_summary(path / "summary.json")
    if (
        manifest.lifecycle != RunLifecycle.COMPLETED
        or manifest.provider_mode != ProviderMode.MOCK
        or manifest.evidence_kind != EvidenceKind.SYNTHETIC
        or manifest.git_sha != expected_git_sha
        or manifest.dirty_worktree
        or manifest.benchmark_sha256 != policy.model.benchmark_sha256
        or len(manifest.pairs) != policy.model.limits.max_cases
        or report.completed_case_count != policy.model.limits.max_cases
        or report.failed_case_count != 0
        or report.missing_cases
    ):
        raise VertexPilotError("Mock dry-run evidence does not satisfy the pilot policy")
    for name in ("summary.json", "report.md", "scores.jsonl", "pairs.jsonl"):
        expected = manifest.artifact_hashes.get(name)
        artifact = path / name
        if expected is None or not artifact.is_file() or file_sha256(artifact) != expected:
            raise VertexPilotError(f"Mock dry-run artifact is invalid: {name}")


def _conservative_committed_cost(
    events: list[UsageEvent],
    policy: LoadedPilotPolicy,
) -> Decimal:
    model = policy.model
    per_gemini = (
        Decimal(model.limits.max_gemini_input_tokens_per_call)
        * model.budget.gemini_flash_input_per_million_tokens_usd
        / Decimal(1_000_000)
        + Decimal(model.limits.max_gemini_output_tokens_per_call)
        * model.budget.gemini_flash_output_per_million_tokens_usd
        / Decimal(1_000_000)
    )
    enhancement_events = sum(event.kind == "enhancement" for event in events)
    requested_images = sum(event.requested_images for event in events)
    return (
        Decimal(enhancement_events)
        * per_gemini
        * Decimal(model.limits.max_enhancement_call_groups_per_case)
        * Decimal(model.limits.max_provider_retry_attempts)
        + Decimal(requested_images)
        * model.budget.imagen_fast_per_image_usd
        * Decimal(model.limits.max_provider_retry_attempts)
    )


def _observed_estimate(ledger: UsageLedger, policy: LoadedPilotPolicy) -> Decimal:
    budget = policy.model.budget
    total = Decimal("0")
    for event in ledger.events:
        if event.kind == "enhancement":
            input_tokens = event.tokens_in or policy.model.limits.max_gemini_input_tokens_per_call
            output_tokens = event.tokens_out or policy.model.limits.max_gemini_output_tokens_per_call
            total += (
                Decimal(input_tokens)
                * budget.gemini_flash_input_per_million_tokens_usd
                / Decimal(1_000_000)
                + Decimal(output_tokens)
                * budget.gemini_flash_output_per_million_tokens_usd
                / Decimal(1_000_000)
            )
        elif event.vertex_charged is True:
            total += Decimal(event.requested_images) * budget.imagen_fast_per_image_usd
    return total


def _write_usage_summary(
    run_dir: Path,
    ledger: UsageLedger,
    policy: LoadedPilotPolicy,
) -> None:
    _atomic_json_write(
        run_dir / "pilot_usage_summary.json",
        build_usage_summary(ledger, policy),
    )


def build_usage_summary(
    ledger: UsageLedger,
    policy: LoadedPilotPolicy,
) -> dict[str, Any]:
    events = ledger.events
    return {
        "schema_version": 1,
        "run_id": ledger.run_id,
        "policy_id": ledger.policy_id,
        "policy_sha256": ledger.policy_sha256,
        "approved_plan_sha256": ledger.approved_plan_sha256,
        "enhancement_http_requests": sum(event.kind == "enhancement" for event in events),
        "generation_http_requests": sum(event.kind == "generation" for event in events),
        "requested_images": sum(event.requested_images for event in events),
        "failed_http_requests": sum(event.status == "failed" for event in events),
        "provider_attempts_recorded": sum(event.provider_attempts or 0 for event in events),
        "tokens_in_recorded": sum(event.tokens_in or 0 for event in events),
        "tokens_out_recorded": sum(event.tokens_out or 0 for event in events),
        "recorded_response_estimate_usd": _money(_observed_estimate(ledger, policy)),
        "conservative_committed_envelope_usd": _money(
            _conservative_committed_cost(list(events), policy)
        ),
        "budget_stop_usd": _money(policy.model.budget.stop_at_usd),
        "billing_scope_limitation": policy.model.budget.limitation,
    }


def _git_metadata() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if sha.returncode != 0 or status.returncode != 0 or not sha.stdout.strip():
        raise VertexPilotError("Cannot determine Git state")
    return sha.stdout.strip(), bool(status.stdout.strip())


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
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


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _nonnegative_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _default_run_id() -> str:
    return f"vertex-pilot-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the approved $20-capped Vertex prompt enhancement pilot."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--approved-plan-sha256", required=True)
    parser.add_argument("--mock-run-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument("--poll-timeout-sec", type=float, default=300.0)
    parser.add_argument("--poll-interval-sec", type=float, default=2.0)
    parser.add_argument("--health-timeout-sec", type=float, default=60.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    run_id = arguments.run_id or _default_run_id()
    if not arguments.execute:
        print(
            "VERTEX PILOT REFUSED: --execute is required after post-dry-run approval.",
            file=sys.stderr,
        )
        return 2
    if not RUN_ID_RE.fullmatch(run_id):
        print("VERTEX PILOT REFUSED: invalid run-id", file=sys.stderr)
        return 2
    try:
        manifest = run_vertex_pilot(
            policy_path=arguments.policy,
            preflight_path=arguments.preflight,
            approved_plan_sha256=arguments.approved_plan_sha256,
            mock_run_dir=arguments.mock_run_dir,
            base_url=arguments.base_url,
            runs_dir=arguments.runs_dir,
            run_id=run_id,
            keep_artifacts=arguments.keep_artifacts,
            poll_timeout_sec=arguments.poll_timeout_sec,
            poll_interval_sec=arguments.poll_interval_sec,
            health_timeout_sec=arguments.health_timeout_sec,
            environ=os.environ,
        )
    except (OSError, ValueError, PilotPolicyError, VertexPilotError, EvaluationRunnerError) as exc:
        print(f"VERTEX PILOT FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "VERTEX PILOT GENERATION COMPLETE — REAL SCORING REQUIRED. "
        f"run_id={manifest.run_id} cases={len(manifest.pairs)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
