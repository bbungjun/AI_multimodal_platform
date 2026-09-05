"""Audit persistence and migration safety contracts."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import CheckConstraint

from app.master_models import MasterAudit


def migration():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/0007_master_audit.py"
    spec = importlib.util.spec_from_file_location("master_audit_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_fields_are_safe_and_constrained():
    table = MasterAudit.__table__
    assert set(table.columns.keys()) == {"request_id", "actor_id", "target_id", "action",
        "source", "reason_code", "payload_fingerprint", "before_value", "after_value", "created_at"}
    assert len(table.foreign_keys) == 2
    checks = " ".join(str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint))
    for value in ("operator_cli", "plan_change", "bonus_grant", "jsonb_typeof", "{64}"):
        assert value in checks


def test_additive_migration_and_append_only_guards(monkeypatch):
    module = migration()
    assert (module.revision, module.down_revision) == ("0007_master_audit", "0006_credit_accounting_persistence")
    operations = Mock()
    monkeypatch.setattr(module, "op", operations)
    module.upgrade()
    assert [c.args[0] for c in operations.create_table.call_args_list] == ["master_audit"]
    sql = " ".join(str(c.args[0]) for c in operations.execute.call_args_list)
    for token in ("UPDATE OR DELETE", "TRUNCATE", "master_audit_append_only", "23514"):
        assert token in sql


def test_populated_downgrade_refuses_before_ddl(monkeypatch):
    module = migration()
    operations = Mock()
    statements = []
    def execute(statement):
        statements.append(str(statement))
        if "EXISTS" in str(statement):
            raise RuntimeError("master_audit_requires_empty_table")
    operations.get_bind.return_value.execute.side_effect = execute
    monkeypatch.setattr(module, "op", operations)
    with pytest.raises(RuntimeError, match="master_audit_requires_empty_table"):
        module.downgrade()
    assert "LOCK TABLE" in " ".join(statements)
    operations.drop_table.assert_not_called()
