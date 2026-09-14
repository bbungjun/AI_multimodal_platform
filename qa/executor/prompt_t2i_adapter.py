"""Compile sanitized DevTools and probe evidence into prompt/T2I contract results."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


class PromptT2IAdapterError(ValueError):
    pass


def read_owned_db_probe(runtime: Any, operation: str, *, job_id: str | None = None) -> dict[str, Any]:
    if operation not in {"counts", "job"} or (operation == "counts") != (job_id is None):
        raise PromptT2IAdapterError("prompt_t2i_probe_request_invalid")
    payload = {"operation": operation, **({} if job_id is None else {"job_id": job_id})}
    try:
        raw = runtime.docker(
            *runtime.compose,
            "exec", "-T", "backend", "python", "tests/prompt_t2i_probe.py",
            input=json.dumps(payload, separators=(",", ":")),
        )
        value = json.loads(raw)
    except Exception as error:
        raise PromptT2IAdapterError("prompt_t2i_probe_execution_failed") from error
    fields = ({"complete", "jobs", "outbox", "reservations"} if operation == "counts"
              else {"complete", "state", "assets", "png_assets", "outbox", "reservations"})
    if (type(value) is not dict or set(value) != fields or value.get("complete") is not True
            or any(type(item) is not int or item < 0
                   for key, item in value.items() if key not in {"complete", "state"})
            or (operation == "job" and value["state"] not in {
                "pending", "enhancing", "queued", "generating", "polling", "downloading",
                "completed", "failed", "cancelled"})):
        raise PromptT2IAdapterError("prompt_t2i_probe_result_invalid")
    return value


@dataclass(frozen=True)
class PromptT2IProbes:
    discard_restores_original: bool
    empty_submission_disabled: bool
    over_limit_status: int
    refusal_jobs: int
    refusal_outbox: int
    refusal_reservations: int
    allowed_state_path: tuple[str, ...]

    def __post_init__(self) -> None:
        if (type(self.discard_restores_original) is not bool
                or type(self.empty_submission_disabled) is not bool
                or type(self.over_limit_status) is not int
                or any(type(value) is not int or value < 0 for value in (
                    self.refusal_jobs, self.refusal_outbox, self.refusal_reservations))
                or not self.allowed_state_path
                or any(state not in {"pending", "running", "completed", "failed", "cancelled"}
                       for state in self.allowed_state_path)):
            raise PromptT2IAdapterError("prompt_t2i_probe_invalid")


def _check_map(browser: dict[str, Any]) -> dict[str, bool]:
    if type(browser) is not dict or set(browser) != {
        "technical_complete", "external_page_requests", "unexpected_console_errors",
        "network_cross_check", "checks", "post_counts", "file",
    }:
        raise PromptT2IAdapterError("prompt_t2i_browser_invalid")
    checks = browser["checks"]
    posts = browser["post_counts"]
    file = browser["file"]
    if (type(checks) is not dict or any(type(value) is not bool for value in checks.values())
            or set(checks) != {"original", "draft", "edited", "accepted", "completed",
                               "payload_matches", "persisted_matches", "image_visible",
                               "empty_disabled"}
            or type(posts) is not dict or set(posts) != {"enhancement", "generation"}
            or any(type(value) is not int or value < 0 for value in posts.values())
            or type(file) is not dict or set(file) != {"decoded", "mime"}
            or type(file["decoded"]) is not bool or file["mime"] not in {None, "image/png"}):
        raise PromptT2IAdapterError("prompt_t2i_browser_invalid")
    return checks


def sanitize_image_journey_report(browser_report: dict[str, Any]) -> dict[str, Any]:
    try:
        image = browser_report["image"]
        checks = image["checks"]
        posts = image["post_counts"]
        file = image["file"]
        browser_checks = browser_report["checks"]
        failures = image["failures"]
        cleaned = {
            "technical_complete": (
                browser_report["cleanup"] == 0 and image["technical_complete"] is True
                and browser_checks["devtools_network_inspected"] is True
                and browser_checks["devtools_console_inspected"] is True
            ),
            "external_page_requests": browser_report["external_page_requests"],
            "unexpected_console_errors": browser_report["unexpected_console_errors"],
            "network_cross_check": browser_checks["devtools_network_inspected"] is True,
            "checks": {
                "original": checks["original"],
                "draft": checks["draft"],
                "edited": checks["edited"],
                "accepted": checks["accepted"],
                "completed": checks["completed"],
                "payload_matches": checks["accepted_generation_payload_matches"],
                "persisted_matches": checks["no_observation_failures"] and not failures,
                "image_visible": checks["completed"],
                "empty_disabled": checks["empty_dom_disabled"]
                and checks["empty_accessibility_disabled"],
            },
            "post_counts": {"enhancement": posts["enhancement"], "generation": posts["generation"]},
            "file": {"decoded": checks["completed"], "mime": file["mime"]},
        }
    except (KeyError, TypeError, AttributeError):
        raise PromptT2IAdapterError("prompt_t2i_journey_report_invalid") from None
    _check_map(cleaned)
    return cleaned


def _observation(assertion_id: str, passed: bool, evidence: list[str]) -> dict[str, Any]:
    return {"id": assertion_id, "passed": passed, "evidence": evidence}


def compile_prompt_t2i_results(
    browser: dict[str, Any],
    probes: PromptT2IProbes,
    *,
    runtime_receipt_ready: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    checks = _check_map(browser)
    technical = (browser["technical_complete"] is True
                 and browser["external_page_requests"] == 0
                 and browser["unexpected_console_errors"] == 0
                 and browser["network_cross_check"] is True
                 and runtime_receipt_ready is True)
    if not technical:
        blocked = ["prompt_t2i_evidence_incomplete"]
        empty = {"selected": True, "verdict": "BLOCKED", "assertions": [],
                 "blocked_reasons": blocked}
        return ({"scenario_id": "prompt_review", **empty},
                {"scenario_id": "t2i_generation", **empty})

    prompt_assertions = [
        _observation("review.request_created", browser["post_counts"]["enhancement"] == 3, ["network"]),
        _observation("review.original_retained_before_accept",
                     checks["original"] and checks["draft"] and checks["edited"], ["ui_snapshot"]),
        _observation("review.discard_restores_original", probes.discard_restores_original, ["ui_snapshot"]),
        _observation("review.accept_applies_edited_draft", checks["accepted"], ["ui_snapshot"]),
        _observation("review.submission_matches_reviewed_input",
                     checks["payload_matches"] and checks["persisted_matches"], ["network", "database"]),
        _observation("review.no_automatic_replacement",
                     checks["original"] and checks["draft"], ["runtime_receipt"]),
    ]
    t2i_assertions = [
        _observation("t2i.empty_submission_disabled",
                     probes.empty_submission_disabled and checks["empty_disabled"], ["ui_snapshot"]),
        _observation("t2i.free_limit_refused", probes.over_limit_status == 403, ["network"]),
        _observation("t2i.refusal_has_zero_jobs", probes.refusal_jobs == 0, ["database"]),
        _observation("t2i.refusal_has_zero_outbox", probes.refusal_outbox == 0, ["database"]),
        _observation("t2i.refusal_has_zero_reservations", probes.refusal_reservations == 0, ["database"]),
        _observation("t2i.allowed_job_completed",
                     probes.allowed_state_path == ("pending", "running", "completed"),
                     ["database", "runtime_receipt"]),
        _observation("t2i.asset_decodes", browser["file"]["decoded"]
                     and browser["file"]["mime"] == "image/png", ["asset_probe"]),
        _observation("t2i.result_visible", checks["completed"] and checks["image_visible"], ["ui_snapshot"]),
    ]
    def result(scenario_id: str, assertions: list[dict[str, Any]]) -> dict[str, Any]:
        return {"scenario_id": scenario_id, "selected": True,
                "verdict": "FAIL" if any(not row["passed"] for row in assertions) else "PASS",
                "assertions": assertions, "blocked_reasons": []}
    return result("prompt_review", prompt_assertions), result("t2i_generation", t2i_assertions)
