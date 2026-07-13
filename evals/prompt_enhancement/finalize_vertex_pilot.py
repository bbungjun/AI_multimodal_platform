from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from pilot import (
    DEFAULT_POLICY_PATH,
    LoadedPilotPolicy,
    PilotPolicyError,
    decide_pilot,
    load_pilot_policy,
)
from run_vertex_pilot import UsageLedger, build_usage_summary
from schemas import (
    EvidenceKind,
    MetricName,
    ProviderMode,
    RunLifecycle,
    file_sha256,
    load_run_manifest,
    load_summary,
    write_report_markdown,
    write_run_manifest,
)


class VertexPilotFinalizationError(RuntimeError):
    """Raised when a real pilot cannot be closed with complete evidence."""


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def finalize_vertex_pilot(
    run_dir: Path | str,
    *,
    policy_path: Path | str = DEFAULT_POLICY_PATH,
    approved_plan_sha256: str,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    directory = Path(run_dir).resolve()
    policy = load_pilot_policy(policy_path)
    if not SHA256_RE.fullmatch(approved_plan_sha256):
        raise VertexPilotFinalizationError("Approved plan SHA-256 is invalid")
    if environ.get("AI_PROVIDER") != ProviderMode.VERTEX.value:
        raise VertexPilotFinalizationError("AI_PROVIDER=vertex is required")

    manifest_path = directory / "manifest.json"
    manifest = load_run_manifest(manifest_path)
    if (
        manifest.lifecycle != RunLifecycle.COMPLETED
        or manifest.provider_mode != ProviderMode.VERTEX
        or manifest.evidence_kind != EvidenceKind.REAL
        or manifest.benchmark_sha256 != policy.model.benchmark_sha256
    ):
        raise VertexPilotFinalizationError(
            "Completed real Vertex pilot manifest does not match the policy"
        )

    report = load_summary(directory / "summary.json")
    _verify_manifest_artifact(directory, manifest.artifact_hashes, "summary.json")
    _verify_manifest_artifact(directory, manifest.artifact_hashes, "report.md")
    if report.run_id != manifest.run_id or report.evidence_kind != EvidenceKind.REAL:
        raise VertexPilotFinalizationError("Summary does not match the real pilot manifest")

    ledger_path = directory / "pilot_usage.json"
    usage_summary_path = directory / "pilot_usage_summary.json"
    try:
        ledger = UsageLedger.model_validate_json(ledger_path.read_text(encoding="utf-8"))
        recorded_usage = json.loads(usage_summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VertexPilotFinalizationError(f"Cannot load pilot usage evidence: {exc}") from exc

    if (
        ledger.run_id != manifest.run_id
        or ledger.policy_id != policy.model.policy_id
        or ledger.policy_sha256 != policy.sha256
        or ledger.approved_plan_sha256 != approved_plan_sha256
    ):
        raise VertexPilotFinalizationError("Usage ledger does not match the approved pilot")
    expected_usage = build_usage_summary(ledger, policy)
    if recorded_usage != expected_usage:
        raise VertexPilotFinalizationError("Usage summary does not match the usage ledger")
    _validate_completed_usage(expected_usage, policy, ledger)

    decision = decide_pilot(report, policy)
    result = {
        **decision,
        "approved_plan_sha256": approved_plan_sha256,
        "benchmark_sha256": policy.model.benchmark_sha256,
        "scorer_profile_sha256": policy.model.scorer_profile_sha256,
        "summary_sha256": file_sha256(directory / "summary.json"),
        "usage_ledger_sha256": file_sha256(ledger_path),
        "usage_summary_sha256": file_sha256(usage_summary_path),
        "usage": expected_usage,
    }
    decision_path = directory / "pilot_decision.json"
    result_path = directory / "pilot_result.md"
    rendered = _render_result(result)

    if "pilot_decision.json" in manifest.artifact_hashes:
        _verify_manifest_artifact(
            directory, manifest.artifact_hashes, "pilot_decision.json"
        )
        _verify_manifest_artifact(directory, manifest.artifact_hashes, "pilot_result.md")
        existing = json.loads(decision_path.read_text(encoding="utf-8"))
        if existing != result or result_path.read_text(encoding="utf-8") != rendered:
            raise VertexPilotFinalizationError(
                "Existing final pilot artifacts differ from recomputed evidence"
            )
        return result

    _write_json(decision_path, result)
    write_report_markdown(result_path, rendered)
    artifact_hashes = dict(manifest.artifact_hashes)
    for name, path in (
        ("pilot_usage.json", ledger_path),
        ("pilot_usage_summary.json", usage_summary_path),
        ("pilot_decision.json", decision_path),
        ("pilot_result.md", result_path),
    ):
        artifact_hashes[name] = file_sha256(path)
    write_run_manifest(
        manifest_path,
        manifest.model_copy(update={"artifact_hashes": artifact_hashes}),
    )
    return result


def _validate_completed_usage(
    usage: Mapping[str, Any],
    policy: LoadedPilotPolicy,
    ledger: UsageLedger,
) -> None:
    limits = policy.model.limits
    expected = {
        "enhancement_http_requests": limits.max_enhancement_http_requests,
        "generation_http_requests": limits.max_generation_http_requests,
        "requested_images": limits.max_generated_images,
        "failed_http_requests": 0,
    }
    mismatches = [key for key, value in expected.items() if usage.get(key) != value]
    if mismatches:
        raise VertexPilotFinalizationError(
            "Completed usage does not match exact pilot caps: " + ", ".join(mismatches)
        )
    if any(event.status != "succeeded" for event in ledger.events):
        raise VertexPilotFinalizationError(
            "Completed usage ledger contains a non-succeeded HTTP request"
        )
    if any(
        (event.provider_attempts or 0) > limits.max_provider_retry_attempts
        for event in ledger.events
    ):
        raise VertexPilotFinalizationError("Provider retry hard cap was exceeded")
    if Decimal(str(usage["conservative_committed_envelope_usd"])) > Decimal(
        str(usage["budget_stop_usd"])
    ):
        raise VertexPilotFinalizationError("Usage exceeds the workload-local budget stop")


def _verify_manifest_artifact(
    run_dir: Path,
    artifact_hashes: Mapping[str, str],
    name: str,
) -> None:
    path = run_dir / name
    expected = artifact_hashes.get(name)
    if expected is None or not path.is_file() or file_sha256(path) != expected:
        raise VertexPilotFinalizationError(f"Invalid manifest artifact: {name}")


def _render_result(result: Mapping[str, Any]) -> str:
    observed = result["observed"]
    usage = result["usage"]
    lines = [
        f"# Prompt Enhancement Vertex Pilot 최종 판정 — {result['run_id']}",
        "",
        "> **20-case real Vertex pilot 범위의 증거입니다. Full benchmark 결론이 아닙니다.**",
        "",
        f"- 판정: `{result['recommendation']}`",
        f"- 완료성: {'충족' if result['all_cases_complete'] else '미충족'}",
        f"- 사전 고정 TIFA 비열등성 허용폭: {result['tifa_noninferiority_margin']:.6f}",
        f"- 정책 SHA-256: `{result['policy_sha256']}`",
        f"- 승인 plan SHA-256: `{result['approved_plan_sha256']}`",
        "",
        "## 전체 지표",
        "",
        "| Metric | Mean delta | Paired bootstrap 95% CI |",
        "| --- | ---: | --- |",
    ]
    for metric in MetricName:
        value = observed[metric.value]
        lines.append(
            f"| {metric.value} | {value['mean_delta']:.6f} | "
            f"[{value['ci95_low']:.6f}, {value['ci95_high']:.6f}] |"
        )
    lines.extend(
        [
            "",
            "## 요청·비용 가드",
            "",
            f"- enhancement HTTP 요청: {usage['enhancement_http_requests']}",
            f"- generation HTTP 요청: {usage['generation_http_requests']}",
            f"- 요청 이미지: {usage['requested_images']}",
            f"- 기록된 최종 response 기반 추정 비용: "
            f"${usage['recorded_response_estimate_usd']}",
            f"- 보수적 committed envelope: ${usage['conservative_committed_envelope_usd']}",
            f"- workload-local stop: ${usage['budget_stop_usd']}",
            f"- 한계: {usage['billing_scope_limitation']}",
            "",
            "## 사전 등록 판정 규칙",
            "",
            f"- Proceed: {result['rules']['proceed']}",
            f"- Stop: {result['rules']['stop']}",
            f"- 그 외: {result['rules']['otherwise']}",
            "",
            "세부 case·언어·category 결과는 `report.md`를 확인합니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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
            handle.write(content)
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
        description="Validate and finalize a completed real Vertex pilot."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", type=Path, default=Path(__file__).parent / "runs")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--approved-plan-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = _parse_args(sys.argv[1:] if argv is None else argv)
    if not RUN_ID_RE.fullmatch(arguments.run_id):
        print("VERTEX PILOT FINALIZATION FAILED: invalid run-id", file=sys.stderr)
        return 2
    try:
        result = finalize_vertex_pilot(
            arguments.runs_dir / arguments.run_id,
            policy_path=arguments.policy,
            approved_plan_sha256=arguments.approved_plan_sha256,
            environ=os.environ,
        )
    except (OSError, ValueError, PilotPolicyError, VertexPilotFinalizationError) as exc:
        print(f"VERTEX PILOT FINALIZATION FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        "VERTEX PILOT FINALIZED. "
        f"run_id={result['run_id']} recommendation={result['recommendation']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
