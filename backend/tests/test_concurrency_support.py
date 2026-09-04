import importlib.util
from pathlib import Path
import pytest
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "concurrency_support", ROOT / "backend/tests/concurrency_support.py"
    )
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_target_requires_owned_postgres_mock():
    load().validate_target(
        "concurrency-verify-123456abcdef",
        make_url("postgresql+asyncpg://credit:x@db:5432/concurrency_verify_123456abcdef"),
        "mock", "test",
    )


@pytest.mark.parametrize("project,provider", [
    ("default", "mock"), ("concurrency-verify-123456abcdef", "vertex")
])
def test_target_refuses_unsafe_values(project, provider):
    with pytest.raises(ValueError, match="target_refused"):
        load().validate_target(
            project,
            make_url("postgresql+asyncpg://credit:x@db:5432/concurrency_verify_123456abcdef"),
            provider, "test",
        )
