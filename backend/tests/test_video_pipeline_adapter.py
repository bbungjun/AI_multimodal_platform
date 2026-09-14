from dataclasses import replace
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa" / "executor"))

from video_pipeline_adapter import (VideoPipelineEvidence, compile_video_pipeline_results,
                                    read_latest_image_source)  # noqa: E402


def evidence():
    return VideoPipelineEvidence(
        True, 0, 0, 0,
        True, 403, 0, ("pending", "running", "completed"), "video/mp4", True,
        True, True, True, ("pending", "running", "completed"), "video/mp4", True,
        True, True, ("blocked", "pending", "running", "completed"), True,
        "completed", "completed", 1, 0, True,
    )


def test_complete_evidence_passes_all_three_scenarios():
    results = compile_video_pipeline_results(evidence())
    assert [row["scenario_id"] for row in results] == [
        "t2v_generation", "i2v_generation", "pipeline_generation"
    ]
    assert [len(row["assertions"]) for row in results] == [6, 6, 8]
    assert all(row["verdict"] == "PASS" for row in results)


def test_free_video_admission_bug_is_fail():
    results = compile_video_pipeline_results(replace(
        evidence(), t2v_over_limit_status=201, t2v_refusal_side_effects=1
    ))
    assert results[0]["verdict"] == "FAIL"
    assert {row["id"] for row in results[0]["assertions"] if not row["passed"]} == {
        "t2v.free_duration_refused", "t2v.refusal_has_zero_side_effects"
    }
    assert results[1]["verdict"] == results[2]["verdict"] == "PASS"


def test_incomplete_tooling_blocks_without_assertions():
    results = compile_video_pipeline_results(replace(evidence(), cleanup_total=1))
    assert all(row["verdict"] == "BLOCKED" and row["assertions"] == [] for row in results)


def test_video_placeholder_must_be_usable_or_explicit():
    results = compile_video_pipeline_results(replace(evidence(), t2v_usable=False, i2v_usable=False))
    assert results[0]["verdict"] == results[1]["verdict"] == "FAIL"


def test_source_probe_returns_ids_only():
    class Runtime:
        compose = []
        def docker(self, *args, input=None):
            assert input == '{"operation":"latest_image_source"}'
            return ('{"complete":true,"job_id":"11111111-1111-4111-8111-111111111111",'
                    '"asset_id":"22222222-2222-4222-8222-222222222222"}')
    assert set(read_latest_image_source(Runtime())) == {"job_id", "asset_id"}
