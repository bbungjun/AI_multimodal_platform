import importlib.util, json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "verify_concurrency", ROOT / "scripts/verify_concurrency.py"
    )
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def payload(module):
    return {"groups": dict.fromkeys(module.GROUPS, True),
            "races": 6, "checks": 180, "complete": True}


def test_fixed_receipt_contract_and_budgets():
    module = load(); value = payload(module)
    assert module.parse_proof(json.dumps(value)) == value
    module.activate()
    assert module.base.WORK_SECONDS <= 360
    assert module.base.CLEANUP_SECONDS <= 60


@pytest.mark.parametrize("change", [
    {"complete": False}, {"races": 5}, {"checks": 179},
    {"groups": {}}, {"private": "x"},
])
def test_bad_receipt_refused(change):
    module = load(); value = payload(module); value.update(change)
    with pytest.raises(module.Failure, match="receipt_invalid"):
        module.parse_proof(json.dumps(value))


@pytest.mark.parametrize("value", [
    "default", "concurrency-verify-123", "concurrency-verify-ABCDEF123456",
    "concurrency-verify-../",
])
def test_project_guard(value):
    module = load()
    with pytest.raises(module.Failure, match="target_refused"):
        module.validate_project(value)


def test_private_env_refused_without_read(tmp_path):
    module = load()
    with pytest.raises(module.Failure, match="env_file_refused"):
        module.Runtime(tmp_path / ".env")
