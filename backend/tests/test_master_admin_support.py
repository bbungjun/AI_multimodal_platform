from pathlib import Path
from runpy import run_path

import pytest
from sqlalchemy.engine import make_url


def load():
    return run_path(str(Path(__file__).with_name("master_admin_support.py")))


def test_fixed_proof_contract():
    module = load()
    assert len(module["GROUPS"]) == 8
    from app.schema_revision import CODE_REVISION
    assert module["HEAD"] == CODE_REVISION
    source = Path(__file__).with_name("master_admin_support.py").read_text()
    assert "pg_blocking_pids" in source and "proof_refuse_audit" in source


@pytest.mark.parametrize("project,host,provider,app_env", [
    ("default", "db", "mock", "test"), ("master-admin-verify-123456abcdef", "remote", "mock", "test"),
    ("master-admin-verify-123456abcdef", "db", "vertex", "test"),
    ("master-admin-verify-123456abcdef", "db", "mock", "production")])
def test_guard_rejects_unsafe_targets(project, host, provider, app_env):
    with pytest.raises(ValueError, match="master_proof_target_refused"):
        load()["validate_target"](project, make_url(f"postgresql://{host}/master_admin_verify_123456abcdef"), provider, app_env)
