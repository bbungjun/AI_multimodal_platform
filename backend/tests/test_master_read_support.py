from pathlib import Path
from runpy import run_path

import pytest
from sqlalchemy.engine import make_url


def load():
    return run_path(str(Path(__file__).with_name("master_read_support.py")))


def test_fixed_read_proof_contract():
    from app.schema_revision import CODE_REVISION
    module = load()
    assert len(module["GROUPS"]) == 8 and module["HEAD"] == CODE_REVISION


@pytest.mark.parametrize("provider,env,host", [("vertex", "test", "db"), ("mock", "production", "db"),
                                            ("mock", "test", "remote")])
def test_target_guard(provider, env, host):
    with pytest.raises(ValueError):
        load()["validate_target"]("master-read-verify-123456abcdef",
            make_url(f"postgresql://{host}/master_read_verify_123456abcdef"), provider, env)
