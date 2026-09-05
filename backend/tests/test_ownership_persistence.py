"""G4.2A schema and admission Interface contracts; no live service dependency."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import postgresql

from app.models import Asset, Job, PromptEnhancement

ROOT = Path(__file__).resolve().parents[2]
OWNER = UUID(int=101)
OTHER = UUID(int=102)


def ownership():
    assert importlib.util.find_spec("app.ownership") is not None, "ownership_interface_missing"
    return importlib.import_module("app.ownership")


@pytest.mark.parametrize("model", [Job, PromptEnhancement])
def test_schema_owner_fk_not_null_no_default_and_composite_index(model):
    importlib.import_module("app.identity_models")
    table = model.__table__
    assert "owner_user_id" in table.c
    column = table.c.owner_user_id
    assert column.nullable is False
    assert column.default is None and column.server_default is None
    assert isinstance(column.type, postgresql.UUID)
    fk = next(iter(column.foreign_keys))
    assert str(fk.column) == "users.id"
    assert fk.ondelete == "RESTRICT"
    assert fk.constraint.name == f"fk_{table.name}_owner_user_id_users"
    index = next(i for i in table.indexes if i.name == f"ix_{table.name}_owner_created_at_id")
    assert [c.name for c in index.columns] == ["owner_user_id", "created_at", "id"]


def test_schema_asset_unique_path_without_duplicated_owner():
    table = Asset.__table__
    assert "owner_user_id" not in table.c
    constraint = next((c for c in table.constraints if c.name == "uq_assets_local_path"), None)
    assert isinstance(constraint, UniqueConstraint)
    assert [c.name for c in constraint.columns] == ["local_path"]


def migration():
    path = ROOT / "backend/migrations/versions/0003_content_ownership.py"
    assert path.is_file(), "ownership_migration_missing"
    spec = importlib.util.spec_from_file_location("ownership_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_migration_parent_and_no_automatic_data_rewrite():
    module = migration()
    assert module.revision == "0003_content_ownership"
    assert module.down_revision == "0002_user_session_persistence"
    source = Path(module.__file__).read_text()
    for forbidden in ("DELETE FROM", "TRUNCATE ", "DROP DATABASE", "server_default", "backfill"):
        assert forbidden not in source


@pytest.mark.parametrize("direction", ["upgrade", "downgrade"])
@pytest.mark.parametrize("nonempty", ["jobs", "assets", "prompt_enhancements", "outbox_events"])
def test_schema_migration_refuses_nonempty_before_ddl(monkeypatch, direction, nonempty):
    module = migration()
    statements = []
    operations = Mock()
    def execute(statement):
        sql = str(statement)
        statements.append(sql)
        result = Mock()
        result.scalar.return_value = nonempty in sql if "EXISTS" in sql else False
        return result
    operations.get_bind.return_value.execute.side_effect = execute
    monkeypatch.setattr(module, "op", operations)
    with pytest.raises(RuntimeError, match="^content_ownership_requires_empty_generation_tables$"):
        getattr(module, direction)()
    locks = [s for s in statements if s.startswith("LOCK TABLE")]
    assert len(locks) == 1
    assert "jobs, assets, prompt_enhancements, outbox_events IN ACCESS EXCLUSIVE MODE" in locks[0]
    assert statements.index(locks[0]) < next(i for i,s in enumerate(statements) if "EXISTS" in s)
    assert any("lock_timeout" in s and "5s" in s for s in statements)
    for call in operations.mock_calls:
        assert call[0].startswith("get_bind"), "DDL must not occur on refusal"


def test_schema_harness_and_verifier_head_parity():
    from app.schema_revision import CODE_REVISION
    from runpy import run_path
    for relative, name in (("scripts/verify_schema_migrations.py", "EXPECTED_REVISION"),
                           ("scripts/verify_auth_sessions.py", "HEAD"),
                           ("scripts/mock_auth_support.py", "REVISION")):
        assert run_path(str(ROOT / relative))[name] == CODE_REVISION
    assert run_path(str(ROOT / "backend/tests/ownership_support.py"))["EXPECTED_REVISION"] == CODE_REVISION


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "master"])
@pytest.mark.parametrize("kind", ["job", "enhancement", "asset"])
@pytest.mark.parametrize("actual_owner", [OTHER, None])
async def test_access_foreign_or_null_owner_is_same_not_found(role, kind, actual_owner):
    module = ownership()
    row = SimpleNamespace(id=UUID(int=201), owner_user_id=actual_owner)
    session = SimpleNamespace(scalars=AsyncMock(return_value=Mock()), execute=AsyncMock(return_value=Mock()))
    session.scalars.return_value.first.return_value = row
    session.execute.return_value.one_or_none.return_value = (row, actual_owner)
    access = module.OwnershipAccess(session, SimpleNamespace(id=OWNER, role=role))
    with pytest.raises(HTTPException) as error:
        await getattr(access, kind)(row.id, intent="mutate" if kind == "job" else "use")
    assert error.value.status_code == 404 and error.value.detail == "content_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["job", "enhancement", "asset"])
async def test_access_missing_is_same_not_found(kind):
    module = ownership()
    session = SimpleNamespace(scalars=AsyncMock(return_value=Mock()), execute=AsyncMock(return_value=Mock()))
    session.scalars.return_value.first.return_value = None
    session.execute.return_value.one_or_none.return_value = None
    access = module.OwnershipAccess(session, SimpleNamespace(id=OWNER, role="master"))
    with pytest.raises(HTTPException) as error:
        await getattr(access, kind)(UUID(int=201), intent="mutate" if kind == "job" else "use")
    assert (error.value.status_code, error.value.detail) == (404, "content_not_found")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["job", "enhancement", "asset"])
async def test_access_scoped_sql_returns_owned_row_without_transaction_effects(kind):
    module = ownership()
    row = SimpleNamespace(id=UUID(int=201), owner_user_id=OWNER)
    session = SimpleNamespace(scalars=AsyncMock(return_value=Mock()), execute=AsyncMock(return_value=Mock()),
                              commit=AsyncMock(), rollback=AsyncMock())
    session.scalars.return_value.first.return_value = row
    session.execute.return_value.one_or_none.return_value = (row, OWNER)
    access = module.OwnershipAccess(session, SimpleNamespace(id=OWNER, role="user"))
    kwargs = {"intent": "mutate" if kind == "job" else "use"}
    if kind != "enhancement":
        kwargs["lock"] = True
    assert await getattr(access, kind)(row.id, **kwargs) is row
    statement = (session.execute if kind == "asset" else session.scalars).call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "owner_user_id =" in sql
    assert OWNER in statement.compile().params.values()
    if kind == "asset":
        assert "JOIN jobs" in sql and "FOR UPDATE OF assets" in sql
    elif kind == "job":
        assert "FOR UPDATE OF jobs" in sql
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["job", "enhancement", "asset"])
async def test_access_unknown_intent_fails_before_query(kind):
    module = ownership()
    session = SimpleNamespace(scalars=AsyncMock(), execute=AsyncMock())
    access = module.OwnershipAccess(session, SimpleNamespace(id=OWNER, role="master"))
    with pytest.raises(ValueError, match="^unsupported_ownership_intent$"):
        await getattr(access, kind)(UUID(int=201), intent="unsupported")
    session.scalars.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.parametrize("left,right", [(OWNER,OTHER), (None,None), (OWNER,None)])
def test_access_same_owner_refuses_mismatch_and_null(left, right):
    module = ownership()
    with pytest.raises(HTTPException) as error:
        module.assert_same_owner(SimpleNamespace(owner_user_id=left), SimpleNamespace(owner_user_id=right))
    assert (error.value.status_code, error.value.detail) == (404, "content_not_found")


def test_access_same_owner_is_side_effect_free():
    module = ownership()
    assert module.assert_same_owner(SimpleNamespace(owner_user_id=OWNER),
                                    SimpleNamespace(owner_user_id=OWNER)) is None
