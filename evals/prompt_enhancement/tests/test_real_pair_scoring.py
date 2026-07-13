from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from finalize_vertex_pilot import finalize_vertex_pilot
from generate_pairs import RunnerConfig, run_pairs
from offline.offline_scorers import load_scorer_profile, metric_adapter_configs
from pilot import load_pilot_policy
from run_vertex_pilot import UsageEvent, UsageLedger, build_usage_summary
from score_real_pairs import score_real_run
from schemas import (
    EvidenceKind,
    MetricName,
    ProviderMode,
    RunLifecycle,
    StatisticsConfig,
    load_run_manifest,
)
from summarize import summarize_run
from tests.test_generate_pairs import FakeEvaluationClient, IncrementingClock


class FakeRealAdapter:
    evidence_kind = EvidenceKind.REAL

    def __init__(self, metric: MetricName, adapter: str, revision: str) -> None:
        self.metric = metric
        self.adapter = adapter
        self.model_revision = revision
        self.closed = False

    def score(self, evaluation_prompt: str, image_bytes: bytes) -> float:
        assert evaluation_prompt
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        return {
            MetricName.VQA_SCORE: 0.5,
            MetricName.IMAGE_REWARD: 0.1,
            MetricName.TIFA: 0.75,
        }[self.metric]

    def close(self) -> None:
        self.closed = True


def test_real_pair_scoring_is_resumable_and_summarizes_real_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    policy = load_pilot_policy()
    profile = load_scorer_profile(policy.scorer_profile_path)
    configs = tuple(metric_adapter_configs(profile))
    config_by_metric = {config.metric: config for config in configs}
    run_id = "vertex-pilot-real-score"
    runs_dir = tmp_path / "runs"
    runner_config = RunnerConfig(
        base_url="http://fake.test",
        benchmark_path=policy.benchmark_path,
        runs_dir=runs_dir,
        run_id=run_id,
        keep_artifacts=True,
        poll_timeout_sec=1,
        poll_interval_sec=0,
        expected_enhancer_model=policy.model.models.enhancer,
        expected_template_version="v1",
        git_sha="4c93a5c",
        dirty_worktree=False,
        provider_mode=ProviderMode.VERTEX,
        evidence_kind=EvidenceKind.REAL,
        metric_adapters=configs,
        statistics=StatisticsConfig(
            bootstrap_seed=policy.model.statistics.bootstrap_seed,
            bootstrap_resamples=policy.model.statistics.bootstrap_resamples,
            tie_thresholds=policy.model.statistics.tie_thresholds,
        ),
    )
    run_pairs(
        runner_config,
        client=FakeEvaluationClient(provider_status="ready"),
        environ={"AI_PROVIDER": "vertex"},
        now=IncrementingClock(),
    )

    adapters: list[FakeRealAdapter] = []

    def factory(metric: MetricName, **_: object) -> FakeRealAdapter:
        config = config_by_metric[metric]
        adapter = FakeRealAdapter(metric, config.adapter, config.model_revision)
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr("score_real_pairs.verify_model_cache", lambda *_: None)
    monkeypatch.setattr("score_real_pairs.resolve_device", lambda _: "cpu")
    monkeypatch.setattr("score_real_pairs.validate_resources", lambda *_: None)
    scores = score_real_run(
        runs_dir / run_id,
        profile_path=policy.scorer_profile_path,
        cache_root=tmp_path / "cache",
        requested_device="cpu",
        environ={"AI_PROVIDER": "vertex"},
        adapter_factory=factory,
        now=IncrementingClock(),
    )

    assert len(scores) == 240
    assert all(adapter.closed for adapter in adapters)
    manifest = load_run_manifest(runs_dir / run_id / "manifest.json")
    assert manifest.lifecycle == RunLifecycle.SUMMARIZING

    report = summarize_run(
        runs_dir / run_id,
        environ={"AI_PROVIDER": "vertex"},
        now=IncrementingClock(),
    )

    assert report.evidence_kind == EvidenceKind.REAL
    assert report.completed_case_count == 20
    assert report.failed_case_count == 0
    markdown = (runs_dir / run_id / "report.md").read_text(encoding="utf-8")
    assert "REAL PAIRED SCORER EVIDENCE" in markdown

    approved_plan_sha256 = "a" * 64
    now = datetime(2026, 7, 13, tzinfo=timezone.utc)
    events = tuple(
        [
            UsageEvent(
                sequence=index + 1,
                kind="enhancement",
                step_name=f"Enhance case-{index}",
                status="succeeded",
                requested_at=now,
                completed_at=now,
                model=policy.model.models.enhancer,
                tokens_in=1200,
                tokens_out=300,
                provider_attempts=1,
            )
            for index in range(20)
        ]
        + [
            UsageEvent(
                sequence=index + 21,
                kind="generation",
                step_name=f"Generate arm-{index}",
                status="succeeded",
                requested_at=now,
                completed_at=now,
                model=policy.model.models.generator,
                requested_images=2,
                provider_attempts=1,
                vertex_charged=True,
            )
            for index in range(40)
        ]
    )
    ledger = UsageLedger(
        schema_version=1,
        run_id=run_id,
        policy_id=policy.model.policy_id,
        policy_sha256=policy.sha256,
        approved_plan_sha256=approved_plan_sha256,
        events=events,
    )
    run_dir = runs_dir / run_id
    (run_dir / "pilot_usage.json").write_text(
        ledger.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "pilot_usage_summary.json").write_text(
        json.dumps(build_usage_summary(ledger, policy), indent=2) + "\n",
        encoding="utf-8",
    )

    decision = finalize_vertex_pilot(
        run_dir,
        approved_plan_sha256=approved_plan_sha256,
        environ={"AI_PROVIDER": "vertex"},
    )
    assert decision["recommendation"] == "revise_or_expand"
    assert decision["usage"]["requested_images"] == 80
    assert finalize_vertex_pilot(
        run_dir,
        approved_plan_sha256=approved_plan_sha256,
        environ={"AI_PROVIDER": "vertex"},
    ) == decision
    finalized = load_run_manifest(run_dir / "manifest.json")
    assert "pilot_decision.json" in finalized.artifact_hashes
    assert "pilot_result.md" in finalized.artifact_hashes
