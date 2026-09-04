"""Fixed proof guards and coverage structure; verifier supplies PostgreSQL result."""
import ast
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

PATH = Path(__file__).with_name("credit_accounting_support.py")


def load():
    spec = importlib.util.spec_from_file_location("accounting_proof", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("change", [
    dict(project="creativeops-login-preview"), dict(project="accounting-verify-../"),
    dict(url=make_url("postgresql://credit@remote:5432/accounting_verify_123456abcdef")),
    dict(url=make_url("postgresql://credit@db:5432/development")),
    dict(url=make_url("postgresql://other@db:5432/accounting_verify_123456abcdef")),
    dict(url=make_url("sqlite:///test")), dict(provider="vertex"), dict(app_env="production"),
])
def test_guard_rejects_other_targets_before_connection(change):
    args = dict(project="accounting-verify-123456abcdef",
                url=make_url("postgresql://credit@db:5432/accounting_verify_123456abcdef"),
                provider="mock", app_env="test")
    args.update(change)
    with pytest.raises(ValueError, match="^accounting_target_refused$"):
        load().validate_target(**args)


def test_fixed_target_head_and_eight_groups():
    proof = load()
    proof.validate_target("accounting-verify-123456abcdef",
                          make_url("postgresql://credit@db:5432/accounting_verify_123456abcdef"),
                          "mock", "test")
    assert proof.HEAD == "0006_credit_accounting_persistence"
    assert proof.GROUPS == ("input_quote", "allocation", "reserve_replay", "settlement",
                            "release", "transaction", "integrity", "concurrency")


def test_fixed_program_has_exact_races_and_no_test_or_sleep_shortcut():
    source = PATH.read_text()
    tree = ast.parse(source)
    compile(tree, "fixed-accounting-proof", "exec")
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(name.startswith(("pytest", "tests.")) for name in imports)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "race"]
    assert len(calls) == 8
    for marker in ("pg_blocking_pids", "wait_event_type='Lock'", "await tx1.commit()",
                   "await tx2.commit()", "SET LOCAL lock_timeout='100ms'",
                   "credit_idempotency_conflict", "monthly_credit_exhausted",
                   "credit_reservation_state_conflict", "await reconstruct()"):
        assert marker in source
    assert "asyncio.sleep" not in source and "DISABLE TRIGGER" not in source


def test_output_is_allowlisted_and_exception_values_are_not_printed():
    tree = ast.parse(PATH.read_text())
    prints = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "print"]
    assert set(prints) == {"print(json.dumps(result))", "print('accounting_proof_failed:' + phase)"}
    assert "sys.exit(124)" in PATH.read_text()
