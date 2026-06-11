from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.models import JobState
from app.services.jobs import i2v_guard


def _sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()


def test_source_asset_lock_statement_uses_for_update():
    asset_id = uuid4()

    statement = i2v_guard.source_asset_for_update_statement(asset_id)
    sql = _sql(statement)

    assert "from assets" in sql
    assert "where assets.id" in sql
    assert "for update" in sql


def test_active_i2v_job_statement_filters_source_asset_and_active_states():
    asset_id = uuid4()

    statement = i2v_guard.active_i2v_job_statement(asset_id)
    sql = _sql(statement)

    assert "from jobs" in sql
    assert "jobs.mode = 'i2v'" in sql
    assert "jobs.source_asset_id" in sql
    assert "jobs.state in" in sql
    assert "'pending'" in sql
    assert "'polling'" in sql
    assert "'completed'" not in sql
    assert "'failed'" not in sql
    assert "'cancelled'" not in sql
    assert "limit 1" in sql


def test_active_i2v_states_match_non_terminal_contract():
    assert i2v_guard.ACTIVE_I2V_STATES == (
        JobState.PENDING,
        JobState.ENHANCING,
        JobState.QUEUED,
        JobState.GENERATING,
        JobState.POLLING,
        JobState.DOWNLOADING,
    )
