import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "personal_usage_support", ROOT / "backend/tests/personal_usage_support.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_personal_usage_target_requires_owned_postgres_mock():
    load().validate_target(
        "personal-usage-verify-123456abcdef",
        make_url(
            "postgresql+asyncpg://credit:x@db:5432/personal_usage_verify_123456abcdef"
        ),
        "mock",
        "test",
    )


@pytest.mark.parametrize(
    "project,url,provider,app_env",
    [
        ("default", "postgresql+asyncpg://credit:x@db:5432/default", "mock", "test"),
        (
            "personal-usage-verify-123456abcdef",
            "postgresql+asyncpg://credit:x@localhost:5432/personal_usage_verify_123456abcdef",
            "mock",
            "test",
        ),
        (
            "personal-usage-verify-123456abcdef",
            "postgresql+asyncpg://credit:x@db:5432/personal_usage_verify_123456abcdef",
            "vertex",
            "test",
        ),
        (
            "personal-usage-verify-123456abcdef",
            "postgresql+asyncpg://credit:x@db:5432/personal_usage_verify_123456abcdef",
            "mock",
            "development",
        ),
    ],
)
def test_personal_usage_target_refuses_unsafe_values(project, url, provider, app_env):
    with pytest.raises(ValueError, match="target_refused"):
        load().validate_target(project, make_url(url), provider, app_env)


def test_personal_usage_proof_contract_is_fixed_and_safe():
    module = load()
    assert module.HEAD == "0006_credit_accounting_persistence"
    assert module.GROUPS == (
        "new_user", "plans", "balance", "meters", "renewal", "active_requests",
        "snapshot_races", "failure_privacy",
    )
    assert module.phase == "guard"
