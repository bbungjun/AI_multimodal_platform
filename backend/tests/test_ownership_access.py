"""Ownership Interface contracts, without live services or privileged defaults."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.models import Asset, Job
from app.ownership import OwnershipAccess

OWNER, OTHER, ITEM, REF = (UUID(int=i) for i in (101, 102, 201, 202))


def actor(role="user"):
    return SimpleNamespace(id=OWNER, role=role)


def job(**changes):
    return SimpleNamespace(id=ITEM, owner_user_id=OWNER, assets=[], parent_job_id=None,
                           retry_of_job_id=None, enhancement_id=None, source_asset_id=None, **changes)


def result(rows):
    return Mock(all=lambda: rows, first=lambda: rows[0] if rows else None,
                one_or_none=lambda: rows[0] if rows else None)


@pytest.mark.parametrize("role,scope,code", [("user","mine",200),("master","mine",200),
    ("master","all",200),("user","all",403),("master","unknown",422)])
def test_access_interface_scope_predicate(role, scope, code):
    access = OwnershipAccess(Mock(), actor(role))
    if code != 200:
        with pytest.raises(HTTPException) as exc:
            access.jobs_statement(scope)
        assert exc.value.status_code == code
    else:
        sql = str(access.jobs_statement(scope).compile(dialect=postgresql.dialect()))
        assert ("WHERE jobs.owner_user_id =" in sql) == (scope == "mine")


@pytest.mark.parametrize("kind,intent", [("job","read"),("job","mutate"),("asset","read"),("asset","use")])
@pytest.mark.parametrize("role", ["user","master"])
@pytest.mark.parametrize("owner", [OWNER, OTHER, None])
async def test_access_interface_read_exception_never_grants_mutation(kind, intent, role, owner):
    row = SimpleNamespace(id=ITEM, owner_user_id=owner)
    session = SimpleNamespace(scalars=AsyncMock(return_value=result([row])),
                              execute=AsyncMock(return_value=result([(row,owner)])))
    access = OwnershipAccess(session, actor(role))
    permitted = owner is not None and (owner == OWNER or role == "master" and intent == "read")
    if permitted:
        assert await getattr(access,kind)(ITEM,intent=intent) is row
    else:
        with pytest.raises(HTTPException) as exc:
            await getattr(access,kind)(ITEM,intent=intent)
        assert (exc.value.status_code,exc.value.detail) == (404,"content_not_found")


@pytest.mark.parametrize("reference", ["parent_job_id","retry_of_job_id","enhancement_id","source_asset_id"])
@pytest.mark.parametrize("owner", [OWNER,OTHER,None,"missing"])
@pytest.mark.parametrize("role", ["user","master"])
async def test_access_interface_batched_reference_integrity(reference,owner,role):
    row = job()
    setattr(row,reference,REF)
    session = SimpleNamespace(execute=AsyncMock(return_value=result([] if owner == "missing" else [(REF,owner)])))
    access = OwnershipAccess(session,actor(role))
    if owner == OWNER:
        await access.validate_read_jobs([row])
    else:
        with pytest.raises(HTTPException) as exc:
            await access.validate_read_jobs([row])
        assert exc.value.detail == "content_not_found"
    assert session.execute.await_count == 1


async def test_access_interface_optional_null_and_blocked_source_no_queries():
    session = SimpleNamespace(execute=AsyncMock())
    row = job(blocked=True)
    await OwnershipAccess(session,actor()).validate_read_jobs([row])
    session.execute.assert_not_called()


async def test_access_interface_wrong_loaded_asset_fails_before_reference_queries():
    row = job()
    row.assets = [SimpleNamespace(job_id=REF)]
    session = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(HTTPException, match="content_not_found"):
        await OwnershipAccess(session,actor("master")).validate_read_jobs([row])
    session.execute.assert_not_called()


@pytest.mark.parametrize("size", [1,20,100])
async def test_access_interface_batch_cost_constant(size):
    rows = [job() for _ in range(size)]
    for row in rows:
        row.parent_job_id = row.retry_of_job_id = row.enhancement_id = row.source_asset_id = REF
    session = SimpleNamespace(execute=AsyncMock(return_value=result([(REF,OWNER)])))
    await OwnershipAccess(session,actor()).validate_read_jobs(rows)
    assert session.execute.await_count == 3


@pytest.mark.parametrize("kind", ["job","asset"])
async def test_access_interface_lock_is_fresh_and_table_scoped(kind):
    row = SimpleNamespace(id=ITEM, owner_user_id=OWNER)
    session = SimpleNamespace(scalars=AsyncMock(return_value=result([row])),
                              execute=AsyncMock(return_value=result([(row,OWNER)])))
    await getattr(OwnershipAccess(session,actor()),kind)(ITEM,intent="mutate" if kind=="job" else "use",lock=True)
    statement = (session.scalars if kind=="job" else session.execute).call_args.args[0]
    assert statement.get_execution_options()["populate_existing"] is True
    assert "FOR UPDATE OF " + ("jobs" if kind=="job" else "assets") in str(statement.compile(dialect=postgresql.dialect()))
