"""Proof guards/coverage structure only; R supplies the actual PostgreSQL result."""
import ast
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy.engine import make_url

PATH = Path(__file__).with_name("credit_lifecycle_support.py")


def load():
    spec = importlib.util.spec_from_file_location("lifecycle_proof",PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("change",[
    dict(project="creativeops-login-preview"),dict(project="credit-verify-../"),
    dict(url=make_url("postgresql://credit@remote:5432/credit_verify_123456abcdef")),
    dict(url=make_url("postgresql://credit@db:5432/development")),
    dict(url=make_url("postgresql://other@db:5432/credit_verify_123456abcdef")),
    dict(url=make_url("sqlite:///test")),dict(provider="vertex"),dict(app_env="production"),
])
def test_guard_rejects_other_targets_before_connection(change):
    args = dict(project="credit-verify-123456abcdef",url=make_url("postgresql://credit@db:5432/credit_verify_123456abcdef"),provider="mock",app_env="test")
    args.update(change)
    with pytest.raises(ValueError,match="^lifecycle_target_refused$"):
        load().validate_target(**args)


def test_fixed_target_and_eight_groups():
    p = load()
    p.validate_target("credit-verify-123456abcdef",make_url("postgresql://credit@db:5432/credit_verify_123456abcdef"),"mock","test")
    assert p.HEAD == "0005_credit_lifecycle_operations"
    assert p.GROUPS == ("init","renewal","plan","bonus","expiry","idempotency","transaction","concurrency")
    assert p.END-p.T == p.timedelta(seconds=2592000)


def test_fixed_program_uses_actual_locks_savepoints_and_append_only_without_pytest():
    source = PATH.read_text()
    tree = ast.parse(source)
    compile(tree,"fixed-proof","exec")
    imports = [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert not any(n.startswith(("pytest","tests.")) for n in imports)
    for text in ("pg_blocking_pids", "wait_event_type='Lock'", "SET LOCAL lock_timeout='100ms'",
                 "await tx1.commit()", "await tx2.commit()", "await tx.rollback()",
                 "credit_operation_append_only", "TRUNCATE credit_operations", "DELETE FROM credit_operations",
                 "UPDATE credit_operations SET outcome=outcome", "replace(finite,replayed=True)",
                 "old.plan == \"free\"", "reconstruct()", "credit_idempotency_conflict"):
        assert text in source
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id == "race"]
    assert len(calls) == 8
    assert "asyncio.sleep" not in source and "DISABLE TRIGGER" not in source


def test_output_is_allowlisted_and_no_exception_values():
    tree = ast.parse(PATH.read_text())
    prints = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id == "print"]
    assert len(prints) == 3
    assert set(prints) == {"print(json.dumps(result))", "print('lifecycle_proof_failed:' + phase)"}
    assert "sys.exit(124)" in PATH.read_text()
