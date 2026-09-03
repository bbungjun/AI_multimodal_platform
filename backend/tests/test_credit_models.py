"""A01/A03-A10/A16 structural contracts; actual enforcement uses isolated S."""
import importlib
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

ROOT = Path(__file__).resolve().parents[2]
TABLES = ("credit_accounts", "credit_cycles", "credit_grants", "credit_ledger_events")


def models():
    assert importlib.util.find_spec("app.credit_models"), "credit_models_missing"
    return importlib.import_module("app.credit_models")


def migration():
    path = ROOT / "backend/migrations/versions/0004_credit_foundation.py"
    assert path.is_file(), "credit_migration_missing"
    spec = importlib.util.spec_from_file_location("credit_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", TABLES)
def test_table_constraints_types_and_no_implicit_money(name):
    m = models()
    table = m.Base.metadata.tables[name]
    sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert name in sql
    assert all(c.name for c in table.constraints)
    for column in table.c:
        assert column.server_default is None
        if column.name.endswith(("microcredits", "_delta")) or column.name == "cycle_index":
            assert isinstance(column.type, BigInteger)
            assert column.default is None and column.nullable is False
        if column.name.endswith("_at"):
            assert isinstance(column.type, DateTime) and column.type.timezone
        if column.name.endswith("_id") or column.name == "id":
            assert isinstance(column.type, postgresql.UUID)
    assert all(fk.ondelete == "RESTRICT" for fk in table.foreign_keys)
    for forbidden in ("balance", "available", "email", "token", "payload", "job_id", "reservation_id"):
        assert forbidden not in table.c


def test_exact_credit_columns_and_nullable_fields():
    m = models()
    expected = {
        "credit_accounts": "user_id cycle_anchor_at plan pending_plan created_at updated_at",
        "credit_cycles": "id user_id cycle_index starts_at ends_at plan allowance_microcredits created_at",
        "credit_grants": "id user_id cycle_id kind created_at expires_at granted_microcredits reserved_microcredits consumed_microcredits expired_microcredits reason_code",
        "credit_ledger_events": "id user_id grant_id kind operation_key rate_card_version granted_delta reserved_delta consumed_delta expired_delta created_at reason_code",
    }
    nullable = {"credit_accounts": {"pending_plan"}, "credit_cycles": set(),
                "credit_grants": {"cycle_id", "expires_at"}, "credit_ledger_events": set()}
    for name in TABLES:
        table = m.Base.metadata.tables[name]
        assert set(table.c.keys()) == set(expected[name].split())
        assert {c.name for c in table.c if c.nullable} == nullable[name]


def test_named_composite_ownership_and_uniqueness():
    m = models()
    for name, target, cols in (("credit_grants", "credit_cycles", ["cycle_id", "user_id"]),
                              ("credit_ledger_events", "credit_grants", ["grant_id", "user_id"])):
        table = m.Base.metadata.tables[name]
        fks = [c for c in table.constraints if isinstance(c, ForeignKeyConstraint)]
        composite = next(c for c in fks if list(c.column_keys) == cols)
        assert [e.target_fullname for e in composite.elements] == [target + ".id", target + ".user_id"]
    cycles = m.CreditCycle.__table__
    assert {tuple(c.columns.keys()) for c in cycles.constraints if isinstance(c, UniqueConstraint)} == {
        ("user_id", "cycle_index"), ("id", "user_id")}
    ledger = m.CreditLedgerEvent.__table__
    assert any(tuple(c.columns.keys()) == ("user_id", "operation_key", "grant_id", "kind")
               for c in ledger.constraints if isinstance(c, UniqueConstraint))
    grant = m.CreditGrant.__table__
    index = next(i for i in grant.indexes if i.unique)
    assert list(index.columns.keys()) == ["cycle_id"]
    assert "base" in str(index.dialect_options["postgresql"]["where"])


def test_check_contracts_and_integer_widening():
    m = models()
    checks = {name: " ".join(str(c.sqltext).lower() for c in m.Base.metadata.tables[name].constraints
                               if isinstance(c, CheckConstraint)) for name in TABLES}
    for token in ("free", "pro", "max", "pending_plan", "updated_at", "cycle_anchor_at"):
        assert token in checks["credit_accounts"]
    for token in ("extract(epoch", "2592000", "cycle_index >= 0", "allowance_microcredits >= 0"):
        assert token in checks["credit_cycles"]
    assert "numeric" in checks["credit_grants"] and "numeric" in checks["credit_ledger_events"]
    for token in ("grant", "adjust", "reserve", "settle", "release", "expire", "operation_key", "rate_card_version"):
        assert token in checks["credit_ledger_events"]


def test_migration_is_frozen_additive_and_registered():
    m = migration()
    assert (m.revision, m.down_revision) == ("0004_credit_foundation", "0003_content_ownership")
    source = Path(m.__file__).read_text()
    assert "import app.credit_models" not in source
    assert "import app.credit_models" in (ROOT / "backend/migrations/env.py").read_text()
    for token in ("DELETE FROM", "TRUNCATE TABLE", "DROP SCHEMA", "create_all", "stamp("):
        assert token not in source
    assert "credit_ledger_append_only" in source
    for event in ("UPDATE", "DELETE", "TRUNCATE"):
        assert event in source


@pytest.mark.parametrize("nonempty", TABLES)
def test_downgrade_refuses_before_any_ddl(monkeypatch, nonempty):
    m = migration()
    op = Mock()
    statements = []
    def execute(sql):
        statements.append(str(sql))
        return Mock(scalar=lambda: "EXISTS" in str(sql) and nonempty in str(sql))
    op.get_bind.return_value.execute.side_effect = execute
    monkeypatch.setattr(m, "op", op)
    with pytest.raises(RuntimeError, match="^credit_foundation_requires_empty_tables$"):
        m.downgrade()
    assert all(call[0].startswith("get_bind") for call in op.mock_calls)
    assert "5s" in statements[0]
    assert all(name in statements[1] for name in TABLES)
    assert "ACCESS EXCLUSIVE" in statements[1]


def test_empty_downgrade_drops_only_new_objects_in_reverse_order(monkeypatch):
    m = migration()
    op = Mock()
    op.get_bind.return_value.execute.return_value.scalar.return_value = False
    monkeypatch.setattr(m, "op", op)
    m.downgrade()
    assert [call.args[0] for call in op.drop_table.call_args_list] == list(reversed(TABLES))


def test_upgrade_uses_no_old_table_ddl_or_data_write(monkeypatch):
    m = migration()
    op = Mock()
    monkeypatch.setattr(m, "op", op)
    m.upgrade()
    assert [call.args[0] for call in op.create_table.call_args_list] == list(TABLES)
    for call in op.mock_calls:
        assert call[0] in {"create_table", "create_index", "execute"}
    assert not op.get_bind.called
