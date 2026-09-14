"""Selection-bound owned runtime for Agent-operated Chrome DevTools QA."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "qa" / "contracts"
IMPACT_ROOT = ROOT / "qa" / "impact"
sys.path.insert(0, str(CONTRACT_ROOT))
sys.path.insert(0, str(IMPACT_ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))

from registry import ContractError, derive_scenario_verdict, load_registry  # noqa: E402
from select_impact import changes_between  # noqa: E402
from selector import ImpactError, REVISION, load_policy, select_impact  # noqa: E402
from verify_mock_oauth_browser import MockOAuthRuntime  # noqa: E402


SCENARIOS = {"auth_login"}
RUN_ID = re.compile(r"^agent-qa-auth-[0-9a-f]{12}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BROWSER_RESULT_KEYS = {"scenario_id", "selected", "verdict", "assertions", "blocked_reasons"}
BROWSER_ASSERTION_KEYS = {"id", "passed", "evidence"}
BROWSER_EVIDENCE_KEYS = {
    "login_control_visible", "workspace_path", "logout_probe_status", "final_path", "network"
}
NETWORK_KEYS = {"route", "status", "method"}
SAFE_ROUTES = {
    "/api/auth/me", "/api/auth/google/start", "/api/auth/google/callback", "/api/auth/logout",
    "/favicon.ico", "/favicon.svg", "/vite.svg",
}


class ExecutorError(RuntimeError):
    pass


def _git(repository_root: Path, arguments: list[str]) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            check=False,
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ExecutorError("executor_git_unavailable") from error
    if result.returncode != 0:
        raise ExecutorError("executor_git_failed")
    return result.stdout


def current_revision(repository_root: Path = ROOT) -> str:
    try:
        value = _git(repository_root, ["rev-parse", "HEAD"]).decode("ascii").strip()
    except UnicodeError as error:
        raise ExecutorError("executor_revision_invalid") from error
    if not REVISION.fullmatch(value):
        raise ExecutorError("executor_revision_invalid")
    return value


def require_clean_tracked_source(repository_root: Path = ROOT) -> None:
    if _git(repository_root, ["status", "--porcelain", "--untracked-files=no"]):
        raise ExecutorError("executor_tracked_source_dirty")


def source_digest(repository_root: Path = ROOT) -> str:
    try:
        names = _git(repository_root, ["ls-files", "-z"]).decode("utf-8").split("\0")
    except UnicodeError as error:
        raise ExecutorError("executor_source_path_invalid") from error
    digest = hashlib.sha256()
    for name in sorted(filter(None, names)):
        path = Path(name)
        lowered = path.name.lower()
        if name.startswith(("docs/", ".omo/")) or path.suffix.lower() == ".md":
            continue
        if (lowered == ".env" or lowered.startswith(".env.") and lowered != ".env.example"
                or lowered.endswith((".pem", ".key", ".p12", ".pfx"))
                or any(token in lowered for token in ("credential", "service-account", "private-key"))):
            raise ExecutorError("executor_secret_path_refused")
        source = repository_root / path
        if not source.is_file():
            raise ExecutorError("executor_tracked_source_missing")
        digest.update(name.encode("utf-8") + b"\0" + source.read_bytes())
    return digest.hexdigest()


def build_selection(base_revision: str, head_revision: str, repository_root: Path = ROOT) -> tuple[Any, dict]:
    if (not REVISION.fullmatch(base_revision) or not REVISION.fullmatch(head_revision)
            or base_revision == head_revision):
        raise ExecutorError("executor_revision_invalid")
    if current_revision(repository_root) != head_revision:
        raise ExecutorError("executor_head_stale")
    require_clean_tracked_source(repository_root)
    registry = load_registry(CONTRACT_ROOT)
    policy = load_policy(IMPACT_ROOT, scenario_ids=registry.by_id())
    try:
        selection = select_impact(
            registry,
            policy,
            changes_between(repository_root, base_revision, head_revision),
            base_revision=base_revision,
            head_revision=head_revision,
        )
    except (ImpactError, ContractError) as error:
        raise ExecutorError(str(error)) from error
    return registry, selection


def _empty_result(code: str) -> dict[str, Any]:
    return {
        "scenario_id": "auth_login",
        "selected": True,
        "verdict": "BLOCKED",
        "assertions": [],
        "blocked_reasons": [code],
    }


def _browser_result(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        raise ExecutorError("executor_browser_report_invalid") from error
    if type(value) is not dict or value.get("scenario_id") != "auth_login":
        raise ExecutorError("executor_browser_report_invalid")
    cleanup = value.get("cleanup")
    if (type(cleanup) is not dict or set(cleanup) != {"browser", "mcp", "vite"}
            or any(type(item) is not int or item < 0 for item in cleanup.values())):
        raise ExecutorError("executor_browser_cleanup_invalid")
    result = value.get("scenario_result")
    if (type(result) is not dict or set(result) != BROWSER_RESULT_KEYS
            or result.get("scenario_id") != "auth_login" or result.get("selected") is not True
            or result.get("verdict") not in {"PASS", "FAIL", "BLOCKED"}
            or type(result.get("assertions")) is not list
            or type(result.get("blocked_reasons")) is not list
            or any(type(reason) is not str or re.fullmatch(r"[a-z][a-z0-9_]{2,63}", reason) is None
                   for reason in result["blocked_reasons"])):
        raise ExecutorError("executor_browser_result_invalid")
    clean_assertions = []
    for assertion in result["assertions"]:
        if (type(assertion) is not dict or set(assertion) != BROWSER_ASSERTION_KEYS
                or type(assertion.get("id")) is not str or type(assertion.get("passed")) is not bool
                or type(assertion.get("evidence")) is not list
                or any(source not in {"ui_snapshot", "url", "network"}
                       for source in assertion["evidence"])):
            raise ExecutorError("executor_browser_result_invalid")
        clean_assertions.append({
            "id": assertion["id"],
            "passed": assertion["passed"],
            "evidence": list(assertion["evidence"]),
        })
    evidence = value.get("evidence")
    if (type(evidence) is not dict or set(evidence) != BROWSER_EVIDENCE_KEYS
            or type(evidence["login_control_visible"]) is not bool
            or evidence["workspace_path"] not in {None, "/generate"}
            or type(evidence["logout_probe_status"]) is not int
            or evidence["final_path"] not in {None, "/login"}
            or type(evidence["network"]) is not list):
        raise ExecutorError("executor_browser_evidence_invalid")
    clean_network = []
    for row in evidence["network"]:
        if (type(row) is not dict or set(row) != NETWORK_KEYS or row["route"] not in SAFE_ROUTES
                or type(row["status"]) is not int or not 100 <= row["status"] <= 599
                or type(row["method"]) is not str or row["method"] not in {"GET", "POST"}):
            raise ExecutorError("executor_browser_evidence_invalid")
        clean_network.append(dict(row))
    clean_evidence = {
        "login_control_visible": evidence["login_control_visible"],
        "workspace_path": evidence["workspace_path"],
        "logout_probe_status": evidence["logout_probe_status"],
        "final_path": evidence["final_path"],
        "network": clean_network,
    }
    clean_result = {
        "scenario_id": "auth_login",
        "selected": True,
        "verdict": result["verdict"],
        "assertions": clean_assertions,
        "blocked_reasons": list(result["blocked_reasons"]),
    }
    safe_browser = {
        "chrome_version": value.get("chrome_version") if type(value.get("chrome_version")) is str else None,
        "mcp_version": value.get("mcp_version") if type(value.get("mcp_version")) is str else None,
        "technical_complete": value.get("technical_complete") is True,
        "external_page_requests": value.get("external_page_requests")
        if type(value.get("external_page_requests")) is int else -1,
        "unexpected_console_errors": value.get("unexpected_console_errors")
        if type(value.get("unexpected_console_errors")) is int else -1,
        "network_cross_check": value.get("network_cross_check") is True,
        "evidence": clean_evidence,
        "cleanup": cleanup,
    }
    return clean_result, safe_browser


def finalize_result(
    contract: dict[str, Any],
    browser_result: dict[str, Any],
    browser_summary: dict[str, Any],
    *,
    runtime_cleanup: int,
    source_unchanged: bool,
) -> dict[str, Any]:
    result = json.loads(json.dumps(browser_result))
    blockers = set(result.get("blocked_reasons", []))
    if not browser_summary.get("technical_complete"):
        blockers.add("devtools_execution_incomplete")
    if browser_summary.get("external_page_requests") != 0:
        blockers.add("external_page_request_detected")
    if browser_summary.get("unexpected_console_errors") != 0:
        blockers.add("unexpected_console_error_detected")
    if not browser_summary.get("network_cross_check"):
        blockers.add("network_cross_check_incomplete")
    cleanup = browser_summary.get("cleanup", {})
    if runtime_cleanup != 0 or any(cleanup.get(name) != 0 for name in ("browser", "mcp", "vite")):
        blockers.add("runtime_cleanup_incomplete")
    if not source_unchanged:
        blockers.add("source_changed_during_execution")
    result["blocked_reasons"] = sorted(blockers)
    if (runtime_cleanup == 0 and source_unchanged and not any(cleanup.values())):
        for assertion in result.get("assertions", []):
            if assertion.get("id") == "auth.logout_invalidates":
                assertion["evidence"] = sorted(set(assertion.get("evidence", [])) | {"runtime_receipt"})
    result["verdict"] = derive_scenario_verdict(contract, result)
    return result


def run_execution(
    base_revision: str,
    head_revision: str,
    scenario_id: str,
    *,
    repository_root: Path = ROOT,
    runtime_factory: Callable[..., Any] = MockOAuthRuntime,
    process_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise ExecutorError("executor_scenario_unsupported")
    registry, selection = build_selection(base_revision, head_revision, repository_root)
    decision = next(row for row in selection["scenario_decisions"] if row["scenario_id"] == scenario_id)
    if not decision["selected"]:
        return {
            "complete": True,
            "scenario_id": scenario_id,
            "verdict": "NOT_APPLICABLE",
            "revision": head_revision,
            "selection_sha256": selection["selection_sha256"],
            "runtime_started": False,
        }

    run_id = "agent-qa-auth-" + uuid4().hex[:12]
    if not RUN_ID.fullmatch(run_id):
        raise ExecutorError("executor_run_id_invalid")
    output = repository_root / "output" / "playwright" / run_id
    output.mkdir(parents=True, exist_ok=False)
    before_digest = source_digest(repository_root)
    runtime = runtime_factory(repository_root / ".env.example")
    runtime.deadline = time.monotonic() + 900
    runtime_cleanup = 1
    browser_result = _empty_result("devtools_execution_incomplete")
    browser_summary: dict[str, Any] = {
        "technical_complete": False,
        "external_page_requests": -1,
        "unexpected_console_errors": -1,
        "network_cross_check": False,
        "evidence": {},
        "cleanup": {"browser": 1, "mcp": 1, "vite": 1},
    }
    process_exit_code = None
    error_code = None
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="creativeops-agent-qa-") as temporary:
            runtime.preflight()
            runtime.start(temporary)
            result = process_runner(
                ["node", str(repository_root / "qa" / "devtools" / "auth-contract.mjs"),
                 runtime.base_url, str(output), str(Path(temporary) / "chrome-profile")],
                cwd=repository_root,
                env=runtime.env,
                timeout=360,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            process_exit_code = result.returncode
            browser_result, browser_summary = _browser_result(output / "browser.json")
    except (Exception, KeyboardInterrupt) as error:
        error_code = "executor_interrupted" if isinstance(error, KeyboardInterrupt) else "executor_execution_failed"
    finally:
        try:
            runtime.cleanup()
            runtime_cleanup = 0
        except Exception:
            error_code = error_code or "executor_runtime_cleanup_failed"
    after_revision = current_revision(repository_root)
    after_digest = source_digest(repository_root)
    source_unchanged = (before_digest == after_digest and head_revision == after_revision)
    contract = registry.by_id()[scenario_id]
    final_result = finalize_result(
        contract,
        browser_result,
        browser_summary,
        runtime_cleanup=runtime_cleanup,
        source_unchanged=source_unchanged,
    )
    if error_code:
        final_result["blocked_reasons"] = sorted(set(final_result["blocked_reasons"]) | {error_code})
        final_result["verdict"] = derive_scenario_verdict(contract, final_result)
    cleanup = {
        "browser": browser_summary["cleanup"].get("browser", 1),
        "mcp": browser_summary["cleanup"].get("mcp", 1),
        "vite": browser_summary["cleanup"].get("vite", 1),
        "runtime": runtime_cleanup,
    }
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "revision": head_revision,
        "registry_sha256": registry.sha256,
        "policy_sha256": selection["policy_sha256"],
        "selection_sha256": selection["selection_sha256"],
        "selection_classification": selection["classification"],
        "selection_rule_ids": decision["rule_ids"],
        "provider": "mock",
        "source_unchanged": source_unchanged,
        "runtime_started": True,
        "process_exit_code": process_exit_code,
        "browser": browser_summary,
        "scenario_result": final_result,
        "cleanup": cleanup,
        "seconds": round(time.monotonic() - started, 3),
        "complete": final_result["verdict"] == "PASS" and process_exit_code == 0
        and source_unchanged and not any(cleanup.values()),
    }
    (output / "execution.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {**report, "report_path": str((output / "execution.json").relative_to(repository_root))}
