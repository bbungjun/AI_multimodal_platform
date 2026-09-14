from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "qa" / "contracts"
sys.path.insert(0, str(CONTRACT_ROOT))

from registry import ContractError, load_registry, validate_receipt  # noqa: E402
from verify_registry import main, pass_receipt  # noqa: E402


EXPECTED_SCENARIOS = {
    "auth_login",
    "prompt_review",
    "t2i_generation",
    "t2v_generation",
    "i2v_generation",
    "pipeline_generation",
    "history_navigation",
    "usage_credits",
    "failure_retry",
    "role_ops_master",
}


def _copy_contracts(tmp_path: Path) -> Path:
    target = tmp_path / "contracts"
    shutil.copytree(CONTRACT_ROOT, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_registry_has_versioned_complete_scenario_set() -> None:
    registry = load_registry()

    assert registry.metadata["schema_version"] == 1
    assert {scenario["id"] for scenario in registry.scenarios} == EXPECTED_SCENARIOS
    assert sum(len(scenario["assertions"]) for scenario in registry.scenarios) == 68
    assert len(registry.sha256) == 64


def test_all_related_source_paths_exist() -> None:
    registry = load_registry()

    missing = [
        source_path
        for scenario in registry.scenarios
        for source_path in scenario["related_paths"]
        if not (REPOSITORY_ROOT / source_path).is_file()
    ]

    assert missing == []


def test_registry_hash_covers_schema_contracts(tmp_path: Path) -> None:
    root = _copy_contracts(tmp_path)
    before = load_registry(root).sha256
    receipt_schema = root / "receipt.schema.v1.json"
    value = json.loads(receipt_schema.read_text(encoding="utf-8"))
    value["description"] = "contract revision"
    _write_json(receipt_schema, value)

    assert load_registry(root).sha256 != before


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("related_paths", ["C:/private/fixture.json"], "scenario_path_refused"),
        ("related_paths", ["../private/fixture.json"], "scenario_path_refused"),
    ],
)
def test_registry_refuses_unsafe_paths(
    tmp_path: Path, field: str, value: list[str], error_code: str
) -> None:
    root = _copy_contracts(tmp_path)
    scenario_path = root / "scenarios" / "auth-login.v1.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario[field] = value
    _write_json(scenario_path, scenario)

    with pytest.raises(ContractError, match=error_code):
        load_registry(root)


def test_registry_refuses_secret_like_contract_fields(tmp_path: Path) -> None:
    root = _copy_contracts(tmp_path)
    scenario_path = root / "scenarios" / "auth-login.v1.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario["assertions"][0]["expected"] = {"authorization": "redacted"}
    _write_json(scenario_path, scenario)

    with pytest.raises(ContractError, match="secret_field_refused"):
        load_registry(root)


@pytest.mark.parametrize("mutation", ["duplicate_scenario", "unknown_evidence"])
def test_registry_refuses_duplicates_and_unknown_vocabulary(
    tmp_path: Path, mutation: str
) -> None:
    root = _copy_contracts(tmp_path)
    if mutation == "duplicate_scenario":
        registry_path = root / "registry.v1.json"
        value = json.loads(registry_path.read_text(encoding="utf-8"))
        value["scenarios"].append(value["scenarios"][0])
        _write_json(registry_path, value)
        expected = "registry_scenarios_invalid"
    else:
        scenario_path = root / "scenarios" / "auth-login.v1.json"
        value = json.loads(scenario_path.read_text(encoding="utf-8"))
        value["assertions"][0]["source"] = "screen_guess"
        _write_json(scenario_path, value)
        expected = "scenario_assertion_invalid"

    with pytest.raises(ContractError, match=expected):
        load_registry(root)


def test_all_evidence_produces_pass_receipt() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)

    assert validate_receipt(receipt, registry, expected_revision="0" * 40) == "PASS"


def test_false_product_assertion_produces_fail() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    receipt["scenario_results"][0]["assertions"][0]["passed"] = False
    receipt["scenario_results"][0]["verdict"] = "FAIL"
    receipt["verdict"] = "FAIL"

    assert validate_receipt(receipt, registry) == "FAIL"


def test_missing_evidence_produces_blocked() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    receipt["scenario_results"][0]["assertions"][0]["evidence"] = []
    receipt["scenario_results"][0]["verdict"] = "BLOCKED"
    receipt["verdict"] = "BLOCKED"

    assert validate_receipt(receipt, registry) == "BLOCKED"


def test_cleanup_or_changed_source_produces_blocked() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    receipt["cleanup"]["browser"] = 1
    receipt["source_unchanged"] = False
    receipt["verdict"] = "BLOCKED"

    assert validate_receipt(receipt, registry) == "BLOCKED"


def test_all_not_applicable_cannot_pass() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    for result in receipt["scenario_results"]:
        result.update(selected=False, verdict="NOT_APPLICABLE", assertions=[])
    receipt["verdict"] = "BLOCKED"

    assert validate_receipt(receipt, registry) == "BLOCKED"


def test_receipt_requires_complete_scenario_coverage() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    receipt["scenario_results"].pop()

    with pytest.raises(ContractError, match="receipt_scenario_coverage_invalid"):
        validate_receipt(receipt, registry)


def test_receipt_refuses_unknown_assertion_and_stale_revision() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    unknown = copy.deepcopy(receipt)
    unknown["scenario_results"][0]["assertions"][0]["id"] = "auth.unknown_check"

    with pytest.raises(ContractError, match="receipt_assertion_unknown"):
        validate_receipt(unknown, registry)
    with pytest.raises(ContractError, match="receipt_revision_stale"):
        validate_receipt(receipt, registry, expected_revision="1" * 40)


def test_receipt_refuses_unstructured_block_reason() -> None:
    registry = load_registry()
    receipt = pass_receipt(registry)
    receipt["scenario_results"][0]["blocked_reasons"] = ["tool unavailable"]

    with pytest.raises(ContractError, match="receipt_blocked_reasons_invalid"):
        validate_receipt(receipt, registry)


def test_known_free_plan_defect_is_a_strict_contract() -> None:
    registry = load_registry()
    t2i = registry.by_id()["t2i_generation"]
    assertions = {assertion["id"]: assertion for assertion in t2i["assertions"]}

    assert assertions["t2i.free_limit_refused"]["operator"] == "policy_refusal"
    assert assertions["t2i.refusal_has_zero_jobs"]["operator"] == "zero"
    assert assertions["t2i.refusal_has_zero_outbox"]["operator"] == "zero"
    assert assertions["t2i.refusal_has_zero_reservations"]["operator"] == "zero"
    t2v = registry.by_id()["t2v_generation"]
    t2v_assertions = {assertion["id"]: assertion for assertion in t2v["assertions"]}
    assert t2v_assertions["t2v.free_duration_refused"]["operator"] == "policy_refusal"


def test_cli_returns_machine_readable_summary(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["complete"] is True
    assert summary["scenarios"] == 10
    assert summary["assertions"] == 68
    assert main(["unexpected"]) == 2
