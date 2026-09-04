import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "verify_prompt_credit", ROOT / "scripts/verify_prompt_credit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(module):
    return dict(
        groups=dict.fromkeys(module.GROUPS, True), races=1,
        checks=module.MINIMUM_CHECKS, provider_calls=1, complete=True,
    )


def test_fixed_receipt_contract():
    module = load()
    value = payload(module)
    assert module.parse_proof(json.dumps(value)) == value


@pytest.mark.parametrize("change", [
    {"complete": False}, {"races": 0}, {"checks": 29},
    {"provider_calls": 0}, {"groups": {}}, {"extra": "private"},
])
def test_partial_receipt_refused(change):
    module = load()
    value = payload(module)
    value.update(change)
    with pytest.raises(module.Failure, match="receipt_invalid"):
        module.parse_proof(json.dumps(value))


@pytest.mark.parametrize("value", [
    "default", "prompt-credit-verify-123", "prompt-credit-verify-ABCDEF123456",
    "prompt-credit-verify-../",
])
def test_project_guard(value):
    module = load()
    with pytest.raises(module.Failure, match="target_refused"):
        module.validate_project(value)


def test_private_env_file_refused_without_read(tmp_path):
    module = load()
    with pytest.raises(module.Failure, match="env_file_refused"):
        module.Runtime(tmp_path / ".env")


def test_runtime_uses_prompt_credit_project(monkeypatch):
    module = load()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    runtime = module.Runtime(ROOT / ".env.example", run=lambda *_a, **_k: "")
    assert runtime.project.startswith("prompt-credit-verify-")
    assert module.MINIMUM_CHECKS == 30


def test_cli_refuses_target_and_cleanup_bypasses():
    module = load()
    for flag in ("--project-name", "--dsn", "--keep-volumes", "--evidence-dir"):
        with pytest.raises(SystemExit):
            module.main([flag, "fixture"])
