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
ACCOUNTING_TABLES = (
    "credit_reservations",
    "credit_reservation_items",
    "credit_reservation_allocations",
    "credit_usage_records",
)


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


def operation_migration():
    path = ROOT / "backend/migrations/versions/0005_credit_lifecycle_operations.py"
    spec = importlib.util.spec_from_file_location("operation_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accounting_migration():
    path = ROOT / "backend/migrations/versions/0006_credit_accounting_persistence.py"
    assert path.is_file(), "accounting_migration_missing"
    spec = importlib.util.spec_from_file_location("accounting_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operation_schema_is_typed_owned_and_immutable():
    table = models().CreditOperation.__table__
    assert set(table.columns.keys()) == set("user_id operation_key kind target_plan amount_microcredits expires_at reason_code rate_card_version effective_at result_cycle_id result_grant_id outcome".split())
    assert {c.name for c in table.columns if c.nullable} == {
        "target_plan", "amount_microcredits", "expires_at", "reason_code", "result_grant_id"}
    assert [c.name for c in table.primary_key] == ["user_id", "operation_key"]
    assert {fk.name for fk in table.foreign_key_constraints} == {
        "fk_credit_operations_account", "fk_credit_operations_cycle_owner", "fk_credit_operations_grant_owner"}
    assert all(fk.ondelete == "RESTRICT" for fk in table.foreign_key_constraints)
    checks = " ".join(str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint))
    for token in ("target_plan IS NOT NULL", "amount_microcredits IS NOT NULL",
                  "reason_code IS NOT NULL", "upgraded", "scheduled", "cancelled",
                  "unchanged", "expires_at > effective_at", "{1,96}"):
        assert token in checks
    assert table.c.operation_key.type.length == 96
    assert table.c.effective_at.type.timezone
    assert isinstance(table.c.amount_microcredits.type, BigInteger)
    assert all(c.server_default is None for c in table.columns)


def test_operation_upgrade_adds_only_one_table_and_no_data(monkeypatch):
    m = operation_migration()
    assert (m.revision, m.down_revision) == ("0005_credit_lifecycle_operations", "0004_credit_foundation")
    op = Mock()
    monkeypatch.setattr(m, "op", op)
    m.upgrade()
    assert [c.args[0] for c in op.create_table.call_args_list] == ["credit_operations"]
    assert [c.args[0] for c in op.create_index.call_args_list] == ["ix_credit_operations_user_effective"]
    sql = " ".join(c.args[0] for c in op.execute.call_args_list)
    for token in ("UPDATE OR DELETE", "TRUNCATE", "credit_operation_append_only", "23514"):
        assert token in sql
    assert not op.get_bind.called


@pytest.mark.parametrize("nonempty", [False, True])
def test_operation_downgrade_guard_before_ddl(monkeypatch, nonempty):
    m = operation_migration()
    op = Mock()
    op.get_bind.return_value.execute.return_value.scalar.return_value = nonempty
    monkeypatch.setattr(m, "op", op)
    if nonempty:
        with pytest.raises(RuntimeError, match="^credit_operations_requires_empty_table$"):
            m.downgrade()
        assert not op.drop_table.called and not op.execute.called
    else:
        m.downgrade()
        op.drop_table.assert_called_once_with("credit_operations")
    statements = [str(c.args[0]) for c in op.get_bind.return_value.execute.call_args_list]
    assert statements[:2] == ["SET LOCAL lock_timeout = '5s'", "LOCK TABLE credit_operations IN ACCESS EXCLUSIVE MODE"]


def test_accounting_tables_have_exact_typed_columns_and_no_implicit_values():
    m = models()
    expected = {
        "credit_reservations": "id user_id reserve_operation_key rate_card_version status reserved_microcredits created_at terminal_operation_key terminal_at terminal_reason_code delivery",
        "credit_reservation_items": "reservation_id user_id meter maximum_units quoted_microcredits",
        "credit_reservation_allocations": "reservation_id grant_id user_id ordinal reserved_microcredits",
        "credit_usage_records": "reservation_id meter user_id terminal_operation_key rate_card_version actual_units charged_microcredits recorded_at source delivery",
    }
    nullable = {
        "credit_reservations": {
            "terminal_operation_key", "terminal_at", "terminal_reason_code", "delivery"
        },
        "credit_reservation_items": set(),
        "credit_reservation_allocations": set(),
        "credit_usage_records": set(),
    }
    for name in ACCOUNTING_TABLES:
        table = m.Base.metadata.tables[name]
        assert set(table.columns.keys()) == set(expected[name].split())
        assert {column.name for column in table.columns if column.nullable} == nullable[name]
        assert all(column.server_default is None for column in table.columns)
        assert all(constraint.name for constraint in table.constraints)
        assert all(fk.ondelete == "RESTRICT" for fk in table.foreign_key_constraints)
        for column in table.columns:
            if column.name.endswith(("_microcredits", "_units")) or column.name == "ordinal":
                assert isinstance(column.type, BigInteger)
            if column.name.endswith("_at"):
                assert isinstance(column.type, DateTime) and column.type.timezone


def test_accounting_owner_keys_uniqueness_indexes_and_checks_are_explicit():
    m = models()
    reservation = m.CreditReservation.__table__
    item = m.CreditReservationItem.__table__
    allocation = m.CreditReservationAllocation.__table__
    usage = m.CreditUsageRecord.__table__

    assert [column.name for column in reservation.primary_key] == ["id"]
    assert [column.name for column in item.primary_key] == ["reservation_id", "meter"]
    assert [column.name for column in allocation.primary_key] == ["reservation_id", "grant_id"]
    assert [column.name for column in usage.primary_key] == ["reservation_id", "meter"]
    assert {fk.name for fk in item.foreign_key_constraints} == {"fk_credit_reservation_items_owner"}
    assert {fk.name for fk in allocation.foreign_key_constraints} == {
        "fk_credit_reservation_allocations_owner", "fk_credit_reservation_allocations_grant_owner"
    }
    assert {fk.name for fk in usage.foreign_key_constraints} == {"fk_credit_usage_records_item_owner"}

    uniques = {
        name: {tuple(constraint.columns.keys()) for constraint in table.constraints
               if isinstance(constraint, UniqueConstraint)}
        for name, table in {
            "reservation": reservation, "item": item,
            "allocation": allocation, "usage": usage,
        }.items()
    }
    assert {("id", "user_id"), ("user_id", "reserve_operation_key")} <= uniques["reservation"]
    assert ("reservation_id", "user_id", "meter") in uniques["item"]
    assert ("reservation_id", "ordinal") in uniques["allocation"]
    assert ("user_id", "terminal_operation_key", "meter") in uniques["usage"]
    terminal_index = next(index for index in reservation.indexes if index.unique)
    assert list(terminal_index.columns.keys()) == ["user_id", "terminal_operation_key"]
    assert "IS NOT NULL" in str(terminal_index.dialect_options["postgresql"]["where"])

    checks = {
        table.name: " ".join(str(c.sqltext) for c in table.constraints
                              if isinstance(c, CheckConstraint))
        for table in (reservation, item, allocation, usage)
    }
    for token in ("held", "settled", "released", "delivered", "partial",
                  "no_deliverable", "terminal_at >= created_at", "{1,96}"):
        assert token in checks["credit_reservations"]
    for meter in ("gemini_input_token", "gemini_output_token", "imagen_fast_image",
                  "imagen_standard_image", "imagen_ultra_image", "veo_fast_ms",
                  "veo_standard_ms"):
        assert meter in checks["credit_reservation_items"]
    assert "maximum_units > 0" in checks["credit_reservation_items"]
    assert "ordinal >= 0" in checks["credit_reservation_allocations"]
    for token in ("provider_reported", "platform_measured", "mock_estimate",
                  "estimated", "actual_units >= 0", "charged_microcredits = 0"):
        assert token in checks["credit_usage_records"]


def test_accounting_migration_is_one_additive_guarded_revision(monkeypatch):
    m = accounting_migration()
    assert (m.revision, m.down_revision) == (
        "0006_credit_accounting_persistence", "0005_credit_lifecycle_operations"
    )
    op = Mock()
    monkeypatch.setattr(m, "op", op)
    m.upgrade()
    assert [call.args[0] for call in op.create_table.call_args_list] == list(ACCOUNTING_TABLES)
    sql = " ".join(str(call.args[0]) for call in op.execute.call_args_list)
    for token in ("credit_reservation_immutable", "credit_accounting_append_only",
                  "UPDATE OR DELETE", "TRUNCATE", "23514"):
        assert token in sql
    assert not op.get_bind.called


@pytest.mark.parametrize("nonempty", ACCOUNTING_TABLES)
def test_accounting_downgrade_refuses_all_four_tables_before_ddl(monkeypatch, nonempty):
    m = accounting_migration()
    op = Mock()
    statements = []

    def execute(sql):
        statements.append(str(sql))
        return Mock(scalar=lambda: "SELECT EXISTS" in str(sql) and nonempty in str(sql))

    op.get_bind.return_value.execute.side_effect = execute
    monkeypatch.setattr(m, "op", op)
    with pytest.raises(RuntimeError, match="^credit_accounting_requires_empty_tables$"):
        m.downgrade()
    assert statements[0] == "SET LOCAL lock_timeout = '5s'"
    assert "ACCESS EXCLUSIVE" in statements[1]
    assert all(name in statements[1] for name in ACCOUNTING_TABLES)
    assert not op.drop_table.called


def test_accounting_empty_downgrade_drops_only_new_objects(monkeypatch):
    m = accounting_migration()
    op = Mock()
    op.get_bind.return_value.execute.return_value.scalar.return_value = False
    monkeypatch.setattr(m, "op", op)
    m.downgrade()
    assert [call.args[0] for call in op.drop_table.call_args_list] == list(reversed(ACCOUNTING_TABLES))
