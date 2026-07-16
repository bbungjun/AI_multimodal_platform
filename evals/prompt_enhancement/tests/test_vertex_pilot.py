from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pilot import build_preflight, decide_pilot, load_pilot_policy
from generate_pairs import HttpRequestError, HttpRequestTimeoutError
from run_vertex_pilot import (
    BudgetedVertexClient,
    VertexPilotError,
    _require_execution_approval,
    _persist_vertex_failure,
    _verify_preflight,
)
from schemas import (
    AggregateReport,
    EvidenceKind,
    MetricAggregate,
    MetricName,
    file_sha256,
)


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls = 0

    def request_json(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
        del method, kwargs
        self.calls += 1
        if path == "/api/prompts/enhance":
            return {
                "id": f"enhancement-{self.calls}",
                "latency_ms": 25,
                "tokens_in": 1200,
                "tokens_out": 300,
            }
        if path == "/api/generations":
            return {
                "id": f"job-{self.calls}",
                "attempts": 0,
                "vertex_charged": False,
            }
        raise AssertionError(path)

    def request_bytes(self, *args: object, **kwargs: object) -> tuple[bytes, dict[str, str], int]:
        del args, kwargs
        return b"", {}, 204


class FailingHttpClient(FakeHttpClient):
    def request_json(self, *args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        raise HttpRequestError(
            "safe test failure",
            status_code=502,
            public_error_code="prompt_enhancement_invalid_response",
            public_error_reason="schema_validation_failed",
            public_error_field="enhanced",
            public_error_source="parsed",
        )


def test_pilot_v2_is_balanced_hash_bound_and_below_approved_budget() -> None:
    policy = load_pilot_policy()
    preflight = build_preflight(policy)

    assert preflight["limits"]["max_cases"] == 20
    assert preflight["limits"]["max_generated_images"] == 80
    assert preflight["limits"]["http_timeout_sec"] == 180.0
    assert preflight["budget"]["approved_usd"] == "20.000000"
    assert preflight["budget"]["normal_estimate_usd"] == "1.728000"
    assert preflight["budget"]["conservative_retry_envelope_usd"] == "5.952000"
    assert preflight["approval"]["provider_execution_approved"] is False


def test_budgeted_client_stops_before_twenty_first_enhancement(tmp_path: Path) -> None:
    policy = load_pilot_policy()
    wrapped = FakeHttpClient()
    client = BudgetedVertexClient(
        wrapped,
        policy=policy,
        run_id="vertex-pilot-test",
        ledger_path=tmp_path / "pilot_usage.json",
        approved_plan_sha256="a" * 64,
    )

    for index in range(20):
        client.request_json(
            "POST",
            "/api/prompts/enhance",
            expected_status=201,
            step_name=f"Enhance case-{index}",
            payload={"prompt": "not-recorded"},
        )

    with pytest.raises(VertexPilotError, match="hard cap"):
        client.request_json(
            "POST",
            "/api/prompts/enhance",
            expected_status=201,
            step_name="Enhance case-20",
            payload={"prompt": "not-recorded"},
        )

    assert wrapped.calls == 20
    assert len(client.ledger.events) == 20
    assert all(event.status == "succeeded" for event in client.ledger.events)
    assert "not-recorded" not in (tmp_path / "pilot_usage.json").read_text(
        encoding="utf-8"
    )


def test_budgeted_client_persists_safe_public_http_failure_metadata(tmp_path: Path) -> None:
    policy = load_pilot_policy()
    client = BudgetedVertexClient(
        FailingHttpClient(),
        policy=policy,
        run_id="vertex-pilot-http-failure",
        ledger_path=tmp_path / "pilot_usage.json",
        approved_plan_sha256="a" * 64,
    )

    with pytest.raises(HttpRequestError):
        client.request_json(
            "POST",
            "/api/prompts/enhance",
            expected_status=201,
            step_name="Enhance safe-case",
            payload={"prompt": "must-not-appear"},
        )

    event = client.ledger.events[0]
    assert event.status == "failed"
    assert event.http_status == 502
    assert event.provider_failure_code == "prompt_enhancement_invalid_response"
    assert event.failure_reason == "schema_validation_failed"
    assert event.failure_field == "enhanced"
    assert event.failure_source == "parsed"
    assert "must-not-appear" not in (tmp_path / "pilot_usage.json").read_text(
        encoding="utf-8"
    )


def test_budgeted_client_persists_client_timeout_metadata(tmp_path: Path) -> None:
    policy = load_pilot_policy()

    class TimeoutHttpClient(FakeHttpClient):
        def request_json(self, *args: object, **kwargs: object) -> dict[str, object]:
            del args, kwargs
            raise HttpRequestTimeoutError(
                "Enhance delayed-case request timed out after 60s",
                timeout_sec=60.0,
            )

    client = BudgetedVertexClient(
        TimeoutHttpClient(),
        policy=policy,
        run_id="vertex-pilot-timeout",
        ledger_path=tmp_path / "pilot_usage.json",
        approved_plan_sha256="a" * 64,
    )

    with pytest.raises(HttpRequestTimeoutError):
        client.request_json(
            "POST",
            "/api/prompts/enhance",
            expected_status=201,
            step_name="Enhance delayed-case",
            payload={"prompt": "must-not-persist"},
        )

    event = client.ledger.events[0]
    assert event.status == "failed"
    assert event.failure_type == "HttpRequestTimeoutError"
    assert event.failure_reason == "client_timeout"
    assert event.timeout_sec == 60.0
    assert event.http_status is None
    assert "must-not-persist" not in (tmp_path / "pilot_usage.json").read_text(
        encoding="utf-8"
    )


def test_persist_vertex_failure_marks_manifest_failed_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeManifest:
        def model_copy(self, *, update: dict[str, object]) -> dict[str, object]:
            captured["update"] = update
            return update

    monkeypatch.setattr("run_vertex_pilot.load_run_manifest", lambda _: FakeManifest())
    monkeypatch.setattr(
        "run_vertex_pilot.write_run_manifest",
        lambda _, manifest: captured.setdefault("manifest", manifest),
    )

    _persist_vertex_failure(
        tmp_path,
        HttpRequestError(
            "raw provider text must not persist",
            status_code=502,
            public_error_code="prompt_enhancement_invalid_response",
        ),
    )

    update = captured["update"]
    assert isinstance(update, dict)
    assert update["lifecycle"].value == "failed"
    assert update["last_error"].code == "prompt_enhancement_invalid_response"
    assert "raw provider text" not in update["last_error"].message


def test_execution_still_requires_post_mock_approval_and_guard() -> None:
    policy = load_pilot_policy()

    with pytest.raises(VertexPilotError, match="execution guard failed"):
        _require_execution_approval({}, policy, "b" * 64)


def test_dirty_preflight_cannot_be_approved(tmp_path: Path, monkeypatch) -> None:
    policy = load_pilot_policy()
    candidate = {
        "approval": {"approvable_clean_revision": False},
        "provider_calls": "none",
    }
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    monkeypatch.setattr("run_vertex_pilot.build_preflight", lambda _: candidate)

    with pytest.raises(VertexPilotError, match="clean revision"):
        _verify_preflight(path, policy, file_sha256(path))


def test_preregistered_decision_requires_primary_gain_and_tifa_noninferiority() -> None:
    policy = load_pilot_policy()
    report = AggregateReport(
        schema_version=1,
        run_id="vertex-pilot-decision",
        evidence_kind=EvidenceKind.REAL,
        generated_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        completed_case_count=20,
        failed_case_count=0,
        metrics=(
            _metric(MetricName.VQA_SCORE, 0.04, 0.01, 0.07),
            _metric(MetricName.IMAGE_REWARD, 0.03, -0.01, 0.08),
            _metric(MetricName.TIFA, -0.01, -0.04, 0.02),
        ),
        slices=(),
        missing_cases=(),
    )

    decision = decide_pilot(report, policy)

    assert decision["recommendation"] == "proceed_to_full_benchmark_review"
    assert decision["tifa_noninferiority_margin"] == 0.05


def _metric(
    metric: MetricName,
    mean_delta: float,
    low: float,
    high: float,
) -> MetricAggregate:
    return MetricAggregate(
        metric=metric,
        case_count=20,
        missing_case_count=0,
        raw_mean=0.5,
        enhanced_mean=0.5 + mean_delta,
        mean_delta=mean_delta,
        median_delta=mean_delta,
        ci95_low=low,
        ci95_high=high,
        wins=12,
        ties=4,
        losses=4,
    )
