from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa" / "executor"))

from prompt_t2i_adapter import (  # noqa: E402
    PromptT2IAdapterError,
    PromptT2IProbes,
    compile_prompt_t2i_results,
)


def browser():
    return {
        "technical_complete": True,
        "external_page_requests": 0,
        "unexpected_console_errors": 0,
        "network_cross_check": True,
        "checks": {"original": True, "draft": True, "edited": True, "accepted": True,
                   "completed": True, "payload_matches": True, "persisted_matches": True,
                   "image_visible": True},
        "post_counts": {"enhancement": 2, "generation": 1},
        "file": {"decoded": True, "mime": "image/png"},
    }


def probes(**changes):
    values = dict(discard_restores_original=True, empty_submission_disabled=True,
                  over_limit_status=403, refusal_jobs=0, refusal_outbox=0,
                  refusal_reservations=0, allowed_state_path=("pending", "running", "completed"))
    values.update(changes)
    return PromptT2IProbes(**values)


def test_complete_evidence_produces_two_pass_results():
    prompt, t2i = compile_prompt_t2i_results(browser(), probes(), runtime_receipt_ready=True)

    assert prompt["verdict"] == "PASS"
    assert len(prompt["assertions"]) == 6
    assert t2i["verdict"] == "PASS"
    assert len(t2i["assertions"]) == 8


def test_free_request_size_defect_is_fail_not_allow_failure():
    prompt, t2i = compile_prompt_t2i_results(
        browser(), probes(over_limit_status=201, refusal_jobs=1, refusal_outbox=1,
                          refusal_reservations=1), runtime_receipt_ready=True)

    assert prompt["verdict"] == "PASS"
    assert t2i["verdict"] == "FAIL"
    assert {row["id"] for row in t2i["assertions"] if not row["passed"]} == {
        "t2i.free_limit_refused", "t2i.refusal_has_zero_jobs",
        "t2i.refusal_has_zero_outbox", "t2i.refusal_has_zero_reservations",
    }


@pytest.mark.parametrize("field", ["technical_complete", "network_cross_check"])
def test_missing_tool_evidence_is_blocked(field):
    value = browser()
    value[field] = False
    prompt, t2i = compile_prompt_t2i_results(value, probes(), runtime_receipt_ready=True)

    assert prompt["verdict"] == t2i["verdict"] == "BLOCKED"
    assert prompt["assertions"] == t2i["assertions"] == []


def test_runtime_receipt_is_mandatory():
    prompt, t2i = compile_prompt_t2i_results(browser(), probes(), runtime_receipt_ready=False)
    assert prompt["verdict"] == t2i["verdict"] == "BLOCKED"


def test_closed_browser_shape_refuses_identity_fields():
    value = browser()
    value["identity"] = "not-allowed"
    with pytest.raises(PromptT2IAdapterError, match="prompt_t2i_browser_invalid"):
        compile_prompt_t2i_results(value, probes(), runtime_receipt_ready=True)
