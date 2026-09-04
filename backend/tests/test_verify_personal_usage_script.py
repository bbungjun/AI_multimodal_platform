import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "verify_personal_usage", ROOT / "scripts/verify_personal_usage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(module):
    return {
        "groups": dict.fromkeys(module.GROUPS, True),
        "races": 3,
        "checks": 160,
        "complete": True,
    }


def test_personal_usage_receipt_contract_and_budgets():
    module = load()
    value = payload(module)
    assert module.parse_proof(json.dumps(value)) == value
    module.activate()
    assert module.base.HEAD == "0006_credit_accounting_persistence"
    assert module.base.WORK_SECONDS == 120
    assert module.base.CLEANUP_SECONDS == 60


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"races": 2},
        {"races": True},
        {"checks": 159},
        {"checks": True},
        {"groups": {}},
        {"groups": dict.fromkeys(load().GROUPS, 1)},
        {"extra": "fixed"},
    ],
)
def test_personal_usage_bad_receipt_refused(change):
    module = load()
    value = payload(module)
    value.update(change)
    with pytest.raises(module.Failure, match="receipt_invalid"):
        module.parse_proof(json.dumps(value))


@pytest.mark.parametrize(
    "value",
    [
        "default",
        "creativeops-login-preview",
        "personal-usage-verify-123",
        "personal-usage-verify-123456ABCDEF",
        "personal-usage-verify-../",
    ],
)
def test_personal_usage_project_guard(value):
    module = load()
    with pytest.raises(module.Failure, match="target_refused"):
        module.validate_project(value)


def test_personal_usage_private_env_refused_without_read(tmp_path):
    module = load()
    with pytest.raises(module.Failure, match="env_file_refused"):
        module.Runtime(tmp_path / ".env")
    with pytest.raises(module.Failure, match="env_file_refused"):
        module.Runtime(tmp_path / ".env.example")


def test_personal_usage_deadline_clamps_and_does_not_retry(monkeypatch):
    module = load()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    clock = [0.0]
    monkeypatch.setattr(module.base.time, "monotonic", lambda: clock[0])
    calls = []
    runtime = module.Runtime(
        ROOT / ".env.example", run=lambda args, **kwargs: calls.append(kwargs) or ""
    )
    clock[0] = 115
    runtime.call(["fixture"])
    assert calls[0]["timeout"] == 5
    clock[0] = 121
    with pytest.raises(module.base.Failure, match="timeout"):
        runtime.call(["fixture"])
    assert len(calls) == 1


def test_personal_usage_config_is_owned_and_forces_proof_target(tmp_path, monkeypatch):
    module = load()
    module.activate()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    config = {
        "services": {
            "db": {"image": "postgres:16", "ports": ["5432"], "healthcheck": {"test": []}},
            "migrate": {"build": {"context": "fixed"}},
            "backend": {},
        }
    }
    runtime = module.Runtime(
        ROOT / ".env.example", run=lambda *args, **kwargs: json.dumps(config)
    )
    runtime.configure(tmp_path)
    selected = json.loads((tmp_path / "compose.json").read_text(encoding="utf-8"))
    assert set(selected["services"]) == {"db", "migrate"}
    assert "ports" not in selected["services"]["db"]
    environment = selected["services"]["migrate"]["environment"]
    assert environment["PERSONAL_USAGE_PROOF_PROJECT"] == runtime.project
    assert "ACCOUNTING_PROOF_PROJECT" not in environment
    assert selected["volumes"]["pgdata"]["labels"][module.base.LABEL] == runtime.nonce


def test_personal_usage_failure_cleanup_refuses_foreign_nonce(monkeypatch):
    module = load()
    module.activate()
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    calls = []
    runtime = module.Runtime(
        ROOT / ".env.example", run=lambda args, **kwargs: calls.append(args) or "foreign"
    )
    runtime.resources = lambda: [("volume", "fixture")]
    with pytest.raises(module.base.Failure, match="cleanup_ownership_refused"):
        runtime.cleanup()
    assert not any("down" in call for call in calls)


def test_personal_usage_command_hides_timeout_and_raw_output(monkeypatch):
    module = load()

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("fixed", 1, output="fixed")

    monkeypatch.setattr(module.base.subprocess, "run", timeout)
    with pytest.raises(module.base.Failure, match="^timeout$"):
        module.base.command([], env={}, timeout=1)
    monkeypatch.setattr(
        module.base.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 1, "fixed", "fixed"),
    )
    with pytest.raises(module.base.Failure, match="^command_failed$"):
        module.base.command([], env={}, timeout=1)


def test_personal_usage_cli_has_no_target_or_cleanup_bypass():
    module = load()
    for flag in ("--project-name", "--dsn", "--source", "--keep-volumes", "--evidence-dir"):
        with pytest.raises(SystemExit):
            module.main([flag, "fixture"])
