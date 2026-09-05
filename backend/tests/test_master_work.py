from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from unittest.mock import AsyncMock
import pytest

from app.master_work import MAX_PENDING_SCAN, MasterWorkError, lock_owner_status, mark_cancelled
from app.models import Job, JobState, utc_now


async def test_owner_lock_is_real_and_missing_owner_refused():
    session = SimpleNamespace(scalar=AsyncMock(return_value="active"))
    assert await lock_owner_status(session, uuid4()) == "active"
    sql = str(session.scalar.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql and "users.id" in sql
    session.scalar.return_value = None
    with pytest.raises(MasterWorkError):
        await lock_owner_status(session, uuid4())
    with pytest.raises(MasterWorkError):
        await lock_owner_status(session, None)


def test_cancellation_uses_terminal_state_and_safe_reason():
    job = Job(state=JobState.PENDING, blocked=True, state_history=[])
    mark_cancelled(job, utc_now())
    assert job.state == JobState.CANCELLED
    assert not job.blocked and job.error["code"] == "user_suspended"
    assert job.state_history[-1]["state"] == "cancelled"
    assert MAX_PENDING_SCAN == 500
