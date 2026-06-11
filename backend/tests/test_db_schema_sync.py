from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import db


class FakeInspector:
    def __init__(
        self,
        *,
        indexes: list[dict[str, object]] | None = None,
        tables: list[str] | None = None,
    ) -> None:
        self.indexes = indexes or []
        self.tables = tables or ["jobs"]

    def get_table_names(self) -> list[str]:
        return self.tables

    def get_indexes(self, _table_name: str) -> list[dict[str, object]]:
        return self.indexes


class FakeResult:
    def __init__(self, first_row: object | None) -> None:
        self.first_row = first_row

    def first(self) -> object | None:
        return self.first_row


class FakeConn:
    def __init__(self, *, dialect_name: str = "postgresql", duplicate=None) -> None:
        self.dialect = SimpleNamespace(name=dialect_name)
        self.duplicate = duplicate
        self.statements: list[str] = []

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "HAVING COUNT(*) > 1" in sql:
            return FakeResult(self.duplicate)
        return FakeResult(None)


def test_sync_active_i2v_unique_index_skips_non_postgres(monkeypatch):
    conn = FakeConn(dialect_name="sqlite")
    monkeypatch.setattr(db, "inspect", lambda _conn: FakeInspector())

    db._sync_jobs_active_i2v_unique_index(conn)

    assert conn.statements == []


def test_sync_active_i2v_unique_index_scans_before_create(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(db, "inspect", lambda _conn: FakeInspector())

    db._sync_jobs_active_i2v_unique_index(conn)

    assert "HAVING COUNT(*) > 1" in conn.statements[0]
    assert "CREATE UNIQUE INDEX" in conn.statements[1]
    assert "uq_jobs_active_i2v_source_asset" in conn.statements[1]


def test_sync_active_i2v_unique_index_refuses_existing_duplicates(monkeypatch):
    conn = FakeConn(duplicate=object())
    monkeypatch.setattr(db, "inspect", lambda _conn: FakeInspector())

    with pytest.raises(RuntimeError, match="duplicate active I2V jobs"):
        db._sync_jobs_active_i2v_unique_index(conn)

    assert len(conn.statements) == 1
    assert "HAVING COUNT(*) > 1" in conn.statements[0]
