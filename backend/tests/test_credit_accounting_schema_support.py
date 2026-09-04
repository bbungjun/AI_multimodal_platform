"""G5C1 fixed proof safety; actual enforcement is verified in isolated Postgres."""
import ast
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

PATH = Path(__file__).with_name("credit_accounting_schema_support.py")


def proof():
    spec = importlib.util.spec_from_file_location("accounting_schema_proof_test", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_proof_compiles_without_test_runtime_or_arbitrary_execution_input():
    source = PATH.read_text()
    compile(source, "accounting-schema-proof", "exec")
    tree = ast.parse(source)
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names]
    assert all(not name.startswith(("pytest", "tests.")) for name in imports)
    assert "asyncpg" in imports and "compare_metadata" in source
    for forbidden in ("argparse", "DISABLE TRIGGER"):
        assert forbidden not in source
    assert "import subprocess" not in source
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}]
    assert source.count("print(") == 3


@pytest.mark.parametrize("change", [
    dict(project="creativeops-login-preview"), dict(project="schema-verify-../"),
    dict(url=make_url("postgresql://remote/test")), dict(url=make_url("sqlite:///test")),
    dict(provider="vertex"), dict(app_env="production"), dict(database="other"),
    dict(database=""),
])
def test_target_guard_refuses_before_database_connect(change):
    values = dict(project="schema-verify-12345678", url=make_url("postgresql://db/test"),
                  provider="mock", app_env="test", database="test")
    values.update(change)
    with pytest.raises(ValueError, match="^accounting_schema_target_refused$"):
        proof().validate_target(**values)


def test_fixed_fixtures_match_the_four_table_contract():
    p = proof()
    assert p.HEAD == "0006_credit_accounting_persistence"
    assert p.ACCOUNTING == ("credit_reservations", "credit_reservation_items",
                            "credit_reservation_allocations", "credit_usage_records")
    assert p.reservation()["status"] == "held"
    assert p.item()["quoted_microcredits"] == 50_000_000
    assert p.allocation()["ordinal"] == 0
    assert p.usage()["source"] == "mock_estimate"


def test_proof_covers_owner_shapes_mutation_and_real_downgrade_guards():
    source = PATH.read_text()
    for token in (
        "fk_credit_reservation_items_owner", "fk_credit_reservation_allocations_owner",
        "fk_credit_reservation_allocations_grant_owner", "fk_credit_usage_records_item_owner",
        "credit_reservation_immutable", "credit_accounting_append_only",
        "TRUNCATE credit_reservations CASCADE", "credit_accounting_requires_empty_tables",
        'await migrate("0005_credit_lifecycle_operations", "lock timeout")',
    ):
        assert token in source
    assert "await outer.rollback()" in source
    assert "await snapshot(connection) == (0, 0, 0, 0)" in source


def test_output_is_closed_and_never_echoes_database_errors():
    source = PATH.read_text()
    tree = ast.parse(source)
    prints = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name) and node.func.id == "print"]
    assert set(prints) == {
        "print(json.dumps({'groups': 4, 'checks': checks, 'downgrade_cases': downgrade_cases}))",
        "print('accounting_schema_proof_failed:' + phase)",
    }
    assert "print(error" not in source and "print(output" not in source
