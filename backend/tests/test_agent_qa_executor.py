from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qa" / "contracts"))
sys.path.insert(0, str(ROOT / "qa" / "impact"))
sys.path.insert(0, str(ROOT / "qa" / "executor"))
sys.path.insert(0, str(ROOT / "scripts"))

from registry import load_registry  # noqa: E402
from selector import Change, load_policy, select_impact  # noqa: E402
import runner  # noqa: E402
import agent_qa_executor  # noqa: E402


def _browser_payload() -> dict:
    assertions = [
        ("auth.login_control_visible", ["ui_snapshot"]),
        ("auth.start_redirect", ["network"]),
        ("auth.callback_redirect", ["network"]),
        ("auth.session_resolves", ["network"]),
        ("auth.workspace_route", ["url"]),
        ("auth.logout_invalidates", ["network"]),
        ("auth.login_route_restored", ["url"]),
    ]
    return {
        "scenario_id": "auth_login",
        "chrome_version": "Chrome/153",
        "mcp_version": "1.9.0",
        "technical_complete": True,
        "external_page_requests": 0,
        "unexpected_console_errors": 0,
        "network_cross_check": True,
        "evidence": {
            "login_control_visible": True,
            "workspace_path": "/generate",
            "logout_probe_status": 401,
            "final_path": "/login",
            "network": [
                {"route": "/api/auth/google/start", "status": 307, "method": "GET"},
                {"route": "/api/auth/google/callback", "status": 303, "method": "GET"},
                {"route": "/api/auth/me", "status": 200, "method": "GET"},
                {"route": "/api/auth/logout", "status": 204, "method": "POST"},
                {"route": "/api/auth/me", "status": 401, "method": "GET"},
            ],
        },
        "scenario_result": {
            "scenario_id": "auth_login",
            "selected": True,
            "verdict": "PASS",
            "assertions": [
                {"id": assertion_id, "passed": True, "evidence": evidence}
                for assertion_id, evidence in assertions
            ],
            "blocked_reasons": [],
        },
        "cleanup": {"browser": 0, "mcp": 0, "vite": 0},
    }


def _selection(path: str) -> tuple[object, dict]:
    registry = load_registry(ROOT / "qa" / "contracts")
    policy = load_policy(ROOT / "qa" / "impact", scenario_ids=registry.by_id())
    selection = select_impact(
        registry,
        policy,
        [Change("M", path)],
        base_revision="1" * 40,
        head_revision="2" * 40,
    )
    return registry, selection


def test_browser_report_rejects_extra_identity_field(tmp_path: Path) -> None:
    payload = _browser_payload()
    payload["evidence"]["email"] = "identity-not-allowed"
    path = tmp_path / "browser.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(runner.ExecutorError, match="executor_browser_evidence_invalid"):
        runner._browser_result(path)


def test_finalize_pass_adds_runtime_receipt_evidence() -> None:
    registry = load_registry(ROOT / "qa" / "contracts")
    payload = _browser_payload()
    path_result = payload["scenario_result"]
    summary = {
        "technical_complete": True,
        "external_page_requests": 0,
        "unexpected_console_errors": 0,
        "network_cross_check": True,
        "cleanup_observed": True,
        "cleanup": {"browser": 0, "mcp": 0, "vite": 0},
    }

    result = runner.finalize_result(
        registry.by_id()["auth_login"],
        path_result,
        summary,
        runtime_cleanup=0,
        source_unchanged=True,
    )

    assert result["verdict"] == "PASS"
    logout = next(row for row in result["assertions"] if row["id"] == "auth.logout_invalidates")
    assert logout["evidence"] == ["network", "runtime_receipt"]


def test_product_failure_remains_fail() -> None:
    registry = load_registry(ROOT / "qa" / "contracts")
    payload = _browser_payload()
    payload["scenario_result"]["assertions"][0]["passed"] = False
    summary = {
        "technical_complete": True,
        "external_page_requests": 0,
        "unexpected_console_errors": 0,
        "network_cross_check": True,
        "cleanup_observed": True,
        "cleanup": {"browser": 0, "mcp": 0, "vite": 0},
    }

    result = runner.finalize_result(
        registry.by_id()["auth_login"], payload["scenario_result"], summary,
        runtime_cleanup=0, source_unchanged=True,
    )

    assert result["verdict"] == "FAIL"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("external_page_requests", 1, "external_page_request_detected"),
        ("unexpected_console_errors", 1, "unexpected_console_error_detected"),
        ("network_cross_check", False, "network_cross_check_incomplete"),
    ],
)
def test_environment_guard_produces_blocked(field: str, value, reason: str) -> None:
    registry = load_registry(ROOT / "qa" / "contracts")
    payload = _browser_payload()
    summary = {
        "technical_complete": True,
        "external_page_requests": 0,
        "unexpected_console_errors": 0,
        "network_cross_check": True,
        "cleanup_observed": True,
        "cleanup": {"browser": 0, "mcp": 0, "vite": 0},
    }
    summary[field] = value

    result = runner.finalize_result(
        registry.by_id()["auth_login"], payload["scenario_result"], summary,
        runtime_cleanup=0, source_unchanged=True,
    )

    assert result["verdict"] == "BLOCKED"
    assert reason in result["blocked_reasons"]


def test_unselected_scenario_does_not_start_runtime(monkeypatch) -> None:
    registry, selection = _selection("frontend/src/pages/UsagePage.tsx")
    monkeypatch.setattr(runner, "build_selection", lambda *args: (registry, selection))

    def refused_runtime(*args, **kwargs):
        raise AssertionError("runtime must not start")

    result = runner.run_execution(
        "1" * 40, "2" * 40, "auth_login", runtime_factory=refused_runtime
    )

    assert result["complete"] is True
    assert result["verdict"] == "NOT_APPLICABLE"
    assert result["runtime_started"] is False


def test_selected_execution_uses_owned_runtime_and_writes_sanitized_report(
    monkeypatch, tmp_path: Path
) -> None:
    registry, selection = _selection("qa/executor/runner.py")
    head = runner.current_revision(ROOT)
    selection["head_revision"] = head
    monkeypatch.setattr(runner, "build_selection", lambda *args: (registry, selection))
    monkeypatch.setattr(runner, "source_digest", lambda *args: "a" * 64)
    monkeypatch.setattr(runner, "current_revision", lambda *args: head)

    class Runtime:
        base_url = "http://127.0.0.1:19000"
        env = {}

        def __init__(self, env_file):
            self.deadline = None

        def preflight(self):
            return None

        def start(self, temporary):
            return None

        def cleanup(self):
            return None

    def process(args, **kwargs):
        output = Path(args[3])
        (output / "browser.json").write_text(json.dumps(_browser_payload()), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    result = runner.run_execution(
        "1" * 40,
        head,
        "auth_login",
        repository_root=ROOT,
        runtime_factory=Runtime,
        process_runner=process,
    )

    assert result["complete"] is True
    assert result["scenario_result"]["verdict"] == "PASS"
    assert result["cleanup"] == {"browser": 0, "mcp": 0, "vite": 0, "runtime": 0}
    report = json.loads((ROOT / result["report_path"]).read_text(encoding="utf-8"))
    assert "email" not in json.dumps(report).lower()


def test_cli_prints_only_summary(monkeypatch, capsys) -> None:
    monkeypatch.setattr(agent_qa_executor, "run_execution", lambda *args: {
        "complete": True,
        "scenario_id": "auth_login",
        "verdict": "NOT_APPLICABLE",
        "runtime_started": False,
        "selection_sha256": "a" * 64,
    })

    assert agent_qa_executor.main([
        "--base", "1" * 40, "--head", "2" * 40, "--scenario", "auth_login"
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "complete": True,
        "scenario_id": "auth_login",
        "verdict": "NOT_APPLICABLE",
        "runtime_started": False,
        "selection_sha256": "a" * 64,
    }
