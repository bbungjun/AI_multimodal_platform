"""Compile sanitized video and Pipeline evidence into Registry scenario results."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def read_latest_image_source(runtime: Any) -> dict[str, str]:
    try:
        raw = runtime.docker(*runtime.compose, "exec", "-T", "backend", "python",
                             "tests/prompt_t2i_probe.py",
                             input='{"operation":"latest_image_source"}')
        value = json.loads(raw)
    except Exception as error:
        raise ValueError("video_source_probe_failed") from error
    if (type(value) is not dict or set(value) != {"complete", "job_id", "asset_id"}
            or value.get("complete") is not True or not UUID.fullmatch(value.get("job_id", ""))
            or not UUID.fullmatch(value.get("asset_id", ""))):
        raise ValueError("video_source_probe_invalid")
    return {"job_id": value["job_id"], "asset_id": value["asset_id"]}


def read_pipeline_probe(runtime: Any) -> dict[str, Any]:
    try:
        raw = runtime.docker(*runtime.compose, "exec", "-T", "backend", "python",
                             "tests/prompt_t2i_probe.py", input='{"operation":"latest_pipeline"}')
        value = json.loads(raw)
    except Exception as error:
        raise ValueError("pipeline_probe_failed") from error
    fields = {"complete", "same_owner", "source_linked", "parent_state", "child_state",
              "reservations", "held"}
    if (type(value) is not dict or set(value) != fields or value.get("complete") is not True
            or type(value["same_owner"]) is not bool or type(value["source_linked"]) is not bool
            or value["parent_state"] not in {"completed", "failed", "cancelled"}
            or value["child_state"] not in {"completed", "failed", "cancelled"}
            or type(value["reservations"]) is not int or type(value["held"]) is not int):
        raise ValueError("pipeline_probe_invalid")
    return value


@dataclass(frozen=True)
class VideoPipelineEvidence:
    technical_complete: bool
    external_requests: int
    console_errors: int
    cleanup_total: int
    t2v_empty_disabled: bool
    t2v_over_limit_status: int
    t2v_refusal_side_effects: int
    t2v_state_path: tuple[str, ...]
    t2v_mime: str | None
    t2v_usable: bool
    i2v_no_source_disabled: bool
    i2v_selected_asset_retained: bool
    i2v_job_uses_selected_asset: bool
    i2v_state_path: tuple[str, ...]
    i2v_mime: str | None
    i2v_usable: bool
    pipeline_incomplete_disabled: bool
    pipeline_same_owner: bool
    pipeline_child_state_path: tuple[str, ...]
    pipeline_child_uses_parent_asset: bool
    pipeline_parent_state: str
    pipeline_child_state: str
    pipeline_reservations: int
    pipeline_held_after_terminal: int
    pipeline_survives_reload: bool

    def ready(self) -> bool:
        return (self.technical_complete is True and self.external_requests == 0
                and self.console_errors == 0 and self.cleanup_total == 0)


def _assertion(identifier: str, passed: bool, evidence: list[str]) -> dict[str, Any]:
    return {"id": identifier, "passed": passed, "evidence": evidence}


def _result(identifier: str, assertions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"scenario_id": identifier, "selected": True,
            "verdict": "FAIL" if any(not row["passed"] for row in assertions) else "PASS",
            "assertions": assertions, "blocked_reasons": []}


def compile_video_pipeline_results(e: VideoPipelineEvidence) -> tuple[dict[str, Any], ...]:
    if not e.ready():
        def blocked(identifier: str) -> dict[str, Any]:
            return {"scenario_id": identifier, "selected": True, "verdict": "BLOCKED",
                    "assertions": [], "blocked_reasons": ["video_pipeline_evidence_incomplete"]}
        return tuple(blocked(identifier) for identifier in (
            "t2v_generation", "i2v_generation", "pipeline_generation"))
    t2v = [
        _assertion("t2v.empty_submission_disabled", e.t2v_empty_disabled, ["ui_snapshot"]),
        _assertion("t2v.free_duration_refused", e.t2v_over_limit_status == 403, ["network"]),
        _assertion("t2v.refusal_has_zero_side_effects", e.t2v_refusal_side_effects == 0, ["database"]),
        _assertion("t2v.allowed_job_completed", e.t2v_state_path == ("pending", "running", "completed"),
                   ["database", "runtime_receipt"]),
        _assertion("t2v.asset_mime", e.t2v_mime == "video/mp4", ["asset_probe"]),
        _assertion("t2v.outcome_is_usable", e.t2v_usable, ["ui_snapshot", "asset_probe"]),
    ]
    i2v = [
        _assertion("i2v.no_source_disabled", e.i2v_no_source_disabled, ["ui_snapshot"]),
        _assertion("i2v.selected_asset_retained", e.i2v_selected_asset_retained, ["ui_snapshot"]),
        _assertion("i2v.job_uses_selected_asset", e.i2v_job_uses_selected_asset, ["database"]),
        _assertion("i2v.job_completed", e.i2v_state_path == ("pending", "running", "completed"),
                   ["database", "runtime_receipt"]),
        _assertion("i2v.asset_mime", e.i2v_mime == "video/mp4", ["asset_probe"]),
        _assertion("i2v.outcome_is_usable", e.i2v_usable, ["ui_snapshot", "asset_probe"]),
    ]
    pipeline = [
        _assertion("pipeline.incomplete_submission_disabled", e.pipeline_incomplete_disabled, ["ui_snapshot"]),
        _assertion("pipeline.jobs_share_owner", e.pipeline_same_owner, ["database"]),
        _assertion("pipeline.child_waits_for_parent_asset",
                   e.pipeline_child_state_path == ("blocked", "pending", "running", "completed"),
                   ["database", "runtime_receipt"]),
        _assertion("pipeline.child_uses_parent_asset", e.pipeline_child_uses_parent_asset, ["database"]),
        _assertion("pipeline.parent_completed", e.pipeline_parent_state == "completed", ["database"]),
        _assertion("pipeline.child_completed", e.pipeline_child_state == "completed", ["database"]),
        _assertion("pipeline.single_reservation_settled",
                   e.pipeline_reservations == 1 and e.pipeline_held_after_terminal == 0,
                   ["database", "usage_read_model"]),
        _assertion("pipeline.results_survive_reload", e.pipeline_survives_reload, ["ui_snapshot"]),
    ]
    return (_result("t2v_generation", t2v), _result("i2v_generation", i2v),
            _result("pipeline_generation", pipeline))
