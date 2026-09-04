"""Fixed proof safety/structure. The S verifier, not these tests, proves Postgres."""
import ast
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

PATH = Path(__file__).with_name("credit_foundation_support.py")


def proof():
    spec = importlib.util.spec_from_file_location("credit_proof_test", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_program_compiles_without_tests_or_pytest_runtime_dependency():
    source = PATH.read_text()
    compile(source, "credit-proof", "exec")
    tree = ast.parse(source)
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert all(not name.startswith(("pytest", "tests.")) for name in imports)
    assert "asyncpg" in imports
    assert "compare_metadata" in source and "pg_stat_activity" in source
    assert "unique_lock_not_observed" in source and "await a.execute(\"COMMIT\")" in source
    assert "credit_ledger_append_only" in source
    assert "await snapshot(connection, CREDIT) == before" in source


@pytest.mark.parametrize("change", [
    dict(project="creativeops-login-preview"), dict(project="schema-verify-../"),
    dict(url=make_url("postgresql://remote/test")), dict(url=make_url("sqlite:///test")),
    dict(provider="vertex"), dict(app_env="production"), dict(mode="arbitrary"),
    dict(database="other"), dict(database=""),
])
def test_target_guard_refuses_before_connect(change):
    args = dict(project="schema-verify-12345678", url=make_url("postgresql://db/test"),
                provider="mock", app_env="test", mode="credit", database="test")
    args.update(change)
    with pytest.raises(ValueError, match="^credit_proof_target_refused$"):
        proof().validate_target(**args)


@pytest.mark.parametrize("mode", ["additive", "credit"])
def test_only_two_fixed_modes_on_fresh_local_target(mode):
    proof().validate_target("schema-verify-12345678", make_url("postgresql://db/test"), "mock", "test", mode, "test")


def test_default_fixtures_match_named_persistence_contract():
    p = proof()
    assert p.account()["plan"] == "free"
    assert p.cycle()["ends_at"] - p.cycle()["starts_at"] == p.timedelta(seconds=2_592_000)
    assert p.grant()["granted_microcredits"] == 0
    assert p.event()["rate_card_version"] == "v1"
    assert p.HEAD == "0006_credit_accounting_persistence"
    assert set(p.CREDIT) == {"credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events"}


def test_output_is_closed_and_failure_does_not_echo_exception_or_sql():
    tree = ast.parse(PATH.read_text())
    prints = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "print"]
    assert len(prints) == 3
    for node in prints:
        expression = ast.unparse(node)
        assert expression in ('print(json.dumps(result))', "print('credit_proof_failed:' + phase)")
    assert "sys.exit(124)" in PATH.read_text()


def test_populated_four_table_real_round_trip_and_operation_guards_are_additive():
    source = PATH.read_text()
    assert 'await migrate("downgrade", "0004_credit_foundation")' in source
    assert 'credit_operations_requires_empty_table' in source
    assert 'LOCK TABLE credit_operations IN ROW EXCLUSIVE MODE' in source
    assert 'await snapshot(connection, LEGACY+CREDIT) == before and await schema() == old_schema' in source
    assert source.index('"checks": await credit(connection, dsn)') < source.index('await operation_migration(connection)')
    assert 'credit_foundation_requires_empty_tables' in source
    assert 'DISABLE TRIGGER' not in source
