"""Versioned Agent QA scenario Registry and Receipt contract validation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
ASSERTION_ID = re.compile(r"^[a-z][a-z0-9_.]{2,95}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^[a-z][a-z0-9-]{7,63}$")
SECRET_KEYS = {
    "authorization", "cookie", "cookies", "email", "oauth_code", "oauth_state",
    "password", "profile", "prompt", "original_prompt", "enhanced_prompt",
}
SCENARIO_KEYS = {"schema_version", "id", "title_ko", "personas", "goal", "related_paths",
                 "setup", "steps", "assertions", "required_evidence", "exclusions"}
STEP_KEYS = {"id", "intent", "action"}
ASSERTION_KEYS = {"id", "source", "operator", "expected", "evidence"}
SETUP_KEYS = {"provider", "fixture", "destructive"}
RECEIPT_KEYS = {"schema_version", "run_id", "revision", "registry_sha256", "provider",
                "source_unchanged", "scenario_results", "cleanup", "verdict"}
RESULT_KEYS = {"scenario_id", "selected", "verdict", "assertions", "blocked_reasons"}
OBSERVATION_KEYS = {"id", "passed", "evidence"}
CLEANUP_KEYS = {"browser", "mcp", "vite", "runtime"}


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Registry:
    metadata: dict[str, Any]
    scenarios: tuple[dict[str, Any], ...]
    sha256: str

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {scenario["id"]: scenario for scenario in self.scenarios}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        raise ContractError("contract_json_invalid") from error
    if type(value) is not dict:
        raise ContractError("contract_object_required")
    return value


def _closed(value: dict[str, Any], keys: set[str], code: str) -> None:
    if set(value) != keys:
        raise ContractError(code)


def _safe_content(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRET_KEYS:
                raise ContractError("secret_field_refused")
            _safe_content(child)
    elif isinstance(value, list):
        for child in value:
            _safe_content(child)
    elif isinstance(value, str):
        if re.search(r"[\w.+-]+@[\w.-]+", value):
            raise ContractError("account_identifier_refused")
        if re.search(r"(?i)(authorization:|cookie:|bearer\s+[a-z0-9._-]+)", value):
            raise ContractError("secret_value_refused")


def _unique_strings(value: Any, allowed: set[str] | None, code: str) -> list[str]:
    if (type(value) is not list or not value or any(type(item) is not str for item in value)
            or len(value) != len(set(value)) or (allowed is not None and not set(value) <= allowed)):
        raise ContractError(code)
    return value


def _related_path(value: str) -> bool:
    path = PurePosixPath(value)
    return ("\\" not in value and not value.startswith(("/", "~")) and not re.match(r"^[A-Za-z]:", value)
            and ".." not in path.parts and len(path.parts) >= 2 and all(part for part in path.parts))


def _validate_scenario(scenario: dict[str, Any], metadata: dict[str, Any]) -> None:
    _closed(scenario, SCENARIO_KEYS, "scenario_fields_invalid")
    if scenario["schema_version"] != 1 or not ID.fullmatch(scenario["id"]):
        raise ContractError("scenario_identity_invalid")
    if not isinstance(scenario["title_ko"], str) or not scenario["title_ko"].strip():
        raise ContractError("scenario_title_invalid")
    if not isinstance(scenario["goal"], str) or not scenario["goal"].strip():
        raise ContractError("scenario_goal_invalid")
    _unique_strings(scenario["personas"], set(metadata["personas"]), "scenario_personas_invalid")
    paths = _unique_strings(scenario["related_paths"], None, "scenario_paths_invalid")
    if not all(_related_path(path) for path in paths):
        raise ContractError("scenario_path_refused")
    setup = scenario["setup"]
    if type(setup) is not dict:
        raise ContractError("scenario_setup_invalid")
    _closed(setup, SETUP_KEYS, "scenario_setup_invalid")
    if setup["provider"] not in metadata["providers"] or not ID.fullmatch(setup["fixture"]):
        raise ContractError("scenario_setup_invalid")
    if type(setup["destructive"]) is not bool:
        raise ContractError("scenario_setup_invalid")
    steps = scenario["steps"]
    if type(steps) is not list or not steps:
        raise ContractError("scenario_steps_invalid")
    step_ids = []
    for step in steps:
        if type(step) is not dict:
            raise ContractError("scenario_step_invalid")
        _closed(step, STEP_KEYS, "scenario_step_invalid")
        if (not ID.fullmatch(step["id"]) or not isinstance(step["intent"], str) or not step["intent"].strip()
                or step["action"] not in {"navigate", "click", "type", "select", "reload", "observe", "fixture"}):
            raise ContractError("scenario_step_invalid")
        step_ids.append(step["id"])
    if len(step_ids) != len(set(step_ids)):
        raise ContractError("scenario_step_duplicate")
    required = set(_unique_strings(scenario["required_evidence"], set(metadata["evidence_sources"]),
                                   "scenario_evidence_invalid"))
    assertions = scenario["assertions"]
    if type(assertions) is not list or not assertions:
        raise ContractError("scenario_assertions_invalid")
    assertion_ids = []
    for assertion in assertions:
        if type(assertion) is not dict:
            raise ContractError("scenario_assertion_invalid")
        _closed(assertion, ASSERTION_KEYS, "scenario_assertion_invalid")
        evidence = set(_unique_strings(assertion["evidence"], set(metadata["evidence_sources"]),
                                       "scenario_assertion_evidence_invalid"))
        if (not ASSERTION_ID.fullmatch(assertion["id"]) or assertion["source"] not in metadata["evidence_sources"]
                or assertion["operator"] not in metadata["assertion_operators"] or not evidence <= required):
            raise ContractError("scenario_assertion_invalid")
        assertion_ids.append(assertion["id"])
    if len(assertion_ids) != len(set(assertion_ids)):
        raise ContractError("scenario_assertion_duplicate")
    if (type(scenario["exclusions"]) is not list
            or any(type(item) is not str for item in scenario["exclusions"])
            or len(scenario["exclusions"]) != len(set(scenario["exclusions"]))):
        raise ContractError("scenario_exclusions_invalid")
    _safe_content(scenario)


def load_registry(root: Path = ROOT) -> Registry:
    metadata = _read_json(root / "registry.v1.json")
    _closed(metadata, {"schema_version", "registry_id", "verdicts", "personas", "providers",
                       "evidence_sources", "assertion_operators", "scenarios"}, "registry_fields_invalid")
    if metadata["schema_version"] != 1 or metadata["registry_id"] != "creativeops-agent-qa":
        raise ContractError("registry_identity_invalid")
    for key in ("verdicts", "personas", "providers", "evidence_sources", "assertion_operators"):
        _unique_strings(metadata[key], None, "registry_vocabulary_invalid")
    if set(metadata["verdicts"]) != {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}:
        raise ContractError("registry_verdicts_invalid")
    scenario_paths = _unique_strings(metadata["scenarios"], None, "registry_scenarios_invalid")
    scenarios = []
    digest = hashlib.sha256()
    contract_files = [
        "registry.v1.json",
        "scenario.schema.v1.json",
        "receipt.schema.v1.json",
        *scenario_paths,
    ]
    for name in contract_files:
        if name in scenario_paths and not _related_path(name):
            raise ContractError("registry_scenario_path_refused")
        path = root / name
        data = path.read_bytes()
        digest.update(name.encode("utf-8") + b"\0" + data)
        if name in scenario_paths:
            scenario = _read_json(path)
            _validate_scenario(scenario, metadata)
            scenarios.append(scenario)
    ids = [scenario["id"] for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ContractError("registry_scenario_duplicate")
    _safe_content(metadata)
    return Registry(metadata=metadata, scenarios=tuple(scenarios), sha256=digest.hexdigest())


def derive_scenario_verdict(contract: dict[str, Any], result: dict[str, Any]) -> str:
    if result["selected"] is False:
        return "NOT_APPLICABLE"
    observations = {row["id"]: row for row in result["assertions"]}
    required = {row["id"]: set(row["evidence"]) for row in contract["assertions"]}
    if any(row.get("passed") is False for row in observations.values() if row["id"] in required):
        return "FAIL"
    if result["blocked_reasons"] or set(observations) != set(required):
        return "BLOCKED"
    for assertion_id, evidence in required.items():
        row = observations[assertion_id]
        if row.get("passed") is not True or not evidence <= set(row.get("evidence", [])):
            return "BLOCKED"
    return "PASS"


def validate_receipt(receipt: dict[str, Any], registry: Registry, *, expected_revision: str | None = None) -> str:
    _closed(receipt, RECEIPT_KEYS, "receipt_fields_invalid")
    if (receipt["schema_version"] != 1 or not RUN_ID.fullmatch(receipt["run_id"])
            or not REVISION.fullmatch(receipt["revision"]) or not SHA256.fullmatch(receipt["registry_sha256"])
            or receipt["registry_sha256"] != registry.sha256 or receipt["provider"] != "mock"):
        raise ContractError("receipt_identity_invalid")
    if expected_revision is not None and receipt["revision"] != expected_revision:
        raise ContractError("receipt_revision_stale")
    if type(receipt["source_unchanged"]) is not bool:
        raise ContractError("receipt_source_invalid")
    cleanup = receipt["cleanup"]
    if type(cleanup) is not dict:
        raise ContractError("receipt_cleanup_invalid")
    _closed(cleanup, CLEANUP_KEYS, "receipt_cleanup_invalid")
    if any(type(value) is not int or value < 0 for value in cleanup.values()):
        raise ContractError("receipt_cleanup_invalid")
    results = receipt["scenario_results"]
    if type(results) is not list or not results:
        raise ContractError("receipt_results_invalid")
    contracts = registry.by_id()
    seen = set()
    derived = []
    for result in results:
        if type(result) is not dict:
            raise ContractError("receipt_result_invalid")
        _closed(result, RESULT_KEYS, "receipt_result_invalid")
        scenario_id = result["scenario_id"]
        if scenario_id not in contracts or scenario_id in seen or type(result["selected"]) is not bool:
            raise ContractError("receipt_result_invalid")
        seen.add(scenario_id)
        blocked_reasons = result["blocked_reasons"]
        if blocked_reasons:
            _unique_strings(blocked_reasons, None, "receipt_blocked_reasons_invalid")
            if not all(ID.fullmatch(reason) for reason in blocked_reasons):
                raise ContractError("receipt_blocked_reasons_invalid")
        observations = result["assertions"]
        if type(observations) is not list:
            raise ContractError("receipt_assertions_invalid")
        observation_ids = []
        for observation in observations:
            if type(observation) is not dict:
                raise ContractError("receipt_assertion_invalid")
            _closed(observation, OBSERVATION_KEYS, "receipt_assertion_invalid")
            evidence = observation["evidence"]
            if (not ASSERTION_ID.fullmatch(observation["id"]) or type(observation["passed"]) is not bool
                    or type(evidence) is not list or len(evidence) != len(set(evidence))
                    or any(type(item) is not str or item not in registry.metadata["evidence_sources"]
                           for item in evidence)):
                raise ContractError("receipt_assertion_invalid")
            observation_ids.append(observation["id"])
        if len(observation_ids) != len(set(observation_ids)):
            raise ContractError("receipt_assertion_duplicate")
        contract_assertion_ids = {assertion["id"] for assertion in contracts[scenario_id]["assertions"]}
        if not set(observation_ids) <= contract_assertion_ids:
            raise ContractError("receipt_assertion_unknown")
        value = derive_scenario_verdict(contracts[scenario_id], result)
        if result["verdict"] != value:
            raise ContractError("receipt_scenario_verdict_invalid")
        if value == "NOT_APPLICABLE" and (observations or result["blocked_reasons"]):
            raise ContractError("receipt_not_applicable_invalid")
        derived.append(value)
    if seen != set(contracts):
        raise ContractError("receipt_scenario_coverage_invalid")
    selected_count = sum(result["selected"] for result in results)
    aggregate = ("FAIL" if "FAIL" in derived else "BLOCKED" if ("BLOCKED" in derived
                 or selected_count == 0 or not receipt["source_unchanged"] or any(cleanup.values())) else "PASS")
    if receipt["verdict"] != aggregate:
        raise ContractError("receipt_verdict_invalid")
    _safe_content(receipt)
    return aggregate
