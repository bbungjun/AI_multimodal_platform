from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app import ownership
from app.models import Asset, AssetKind, GenerationMode, Job, JobState, PromptEnhancement, utc_now
from app.services.jobs import handlers


ENTRIES = ("t2i", "t2v", "i2v", "poll_t2v", "poll_i2v")
REFERENCES = ("enhancement_id", "parent_job_id", "retry_of_job_id", "source_asset_id")
OWNER = UUID(int=107)
FOREIGN = UUID(int=108)


def execution_job(entry="t2i", **changes):
    mode = GenerationMode(entry.removeprefix("poll_"))
    values = dict(id=uuid4(), owner_user_id=OWNER, mode=mode,
                  model="imagen-4.0-fast-generate-001" if mode == GenerationMode.T2I else "veo-3.0-fast-generate-001",
                  state=JobState.POLLING if entry.startswith("poll_") else JobState.PENDING,
                  prompt="fixture", blocked=False, attempts=0, parameters={}, state_history=[],
                  vertex_charged=False, vertex_operation_name="mock-operation" if entry.startswith("poll_") else None,
                  enhancement_id=None, parent_job_id=None, retry_of_job_id=None, source_asset_id=None,
                  created_at=utc_now(), updated_at=utc_now())
    return Job(**(values | changes))


class ExecutionSession:
    """Real SQL is inspected; deliberately return unscoped rows to test defense."""
    def __init__(self, job):
        self.job = job
        self.rows = {job.id: job}
        self.added = []
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def get(self, model, row_id):
        return self.rows.get(row_id)

    def _selected(self, statement):
        self.statements.append(statement)
        params = statement.compile().params
        row_id = next((value for key, value in params.items() if key.startswith("id_")), None)
        return self.rows.get(row_id)

    async def scalars(self, statement):
        row = self._selected(statement)
        return SimpleNamespace(first=lambda: row)

    async def execute(self, statement):
        asset = self._selected(statement)
        parent = self.rows.get(asset.job_id) if asset else None
        result = (asset, parent.owner_user_id) if parent else None
        return SimpleNamespace(one_or_none=lambda: result)


def linked_session(entry):
    job = execution_job(entry)
    session = ExecutionSession(job)
    enhancement = PromptEnhancement(id=uuid4(), owner_user_id=OWNER)
    parent, retry, asset_job = (execution_job() for _ in range(3))
    asset = Asset(id=uuid4(), job_id=asset_job.id, kind=AssetKind.IMAGE,
                  local_path="fixture/source.png", mime="image/png", size_bytes=1)
    for row in (enhancement, parent, retry, asset_job, asset):
        session.rows[row.id] = row
    for name, row in zip(REFERENCES, (enhancement, parent, retry, asset)):
        setattr(job, name, row.id)
    return job, session


def interface():
    validator = getattr(ownership, "validate_execution_references", None)
    error = getattr(ownership, "OwnershipReferenceMismatch", None)
    assert callable(validator) and isinstance(error, type), "worker ownership Interface is missing"
    return validator, error


def effect_spies(monkeypatch):
    spies = []
    for module, name in ((handlers.imagen,"generate_image"), (handlers.veo,"submit_video"),
                         (handlers.veo,"poll_operation"), (handlers.veo,"poll_operation_name"),
                         (handlers.rate_limit,"acquire"), (handlers.pipeline_link,"fail_blocked_children_for_parent")):
        spy = AsyncMock(side_effect=AssertionError("unexpected_effect"))
        monkeypatch.setattr(module, name, spy)
        spies.append(spy)
    for name in ("read_bytes", "save_bytes"):
        spy = Mock(side_effect=AssertionError("unexpected_effect"))
        monkeypatch.setattr(handlers.storage, name, spy)
        spies.append(spy)
    return spies


@pytest.mark.parametrize("entry", ENTRIES)
@pytest.mark.parametrize("reference", REFERENCES)
@pytest.mark.parametrize("missing", (False, True))
async def test_execution_corrupt_reference_fails_only_current_job_before_effects(entry, reference, missing, monkeypatch):
    job, session = linked_session(entry)
    row = session.rows[getattr(job, reference)]
    target = session.rows[row.job_id] if isinstance(row, Asset) else row
    if missing:
        del session.rows[row.id]
    else:
        target.owner_user_id = FOREIGN
    before = deepcopy((target.owner_user_id, getattr(target,"state",None), getattr(target,"state_history",None)))
    spies = effect_spies(monkeypatch)
    await getattr(handlers, "handle_" + entry.removeprefix("poll_"))(session, job)
    assert job.state == JobState.FAILED
    assert job.error["code"] == "ownership_reference_mismatch"
    assert job.error["retryable"] is False
    assert job.attempts == 0 and session.added == []
    assert (target.owner_user_id, getattr(target,"state",None), getattr(target,"state_history",None)) == before
    for spy in spies:
        spy.assert_not_called()


@pytest.mark.parametrize("entry", ENTRIES)
async def test_execution_null_owner_fails_before_effects(entry, monkeypatch):
    job, session = linked_session(entry)
    job.owner_user_id = None
    spies = effect_spies(monkeypatch)
    await getattr(handlers, "handle_" + entry.removeprefix("poll_"))(session, job)
    assert job.error["code"] == "ownership_reference_mismatch"
    for spy in spies:
        spy.assert_not_called()


@pytest.mark.parametrize("entry", ENTRIES)
async def test_execution_scoped_interface_returns_checked_asset_without_effects(entry):
    validate, _ = interface()
    job, session = linked_session(entry)
    result = await validate(session, job)
    assert result is session.rows[job.source_asset_id]
    assert session.commits == session.rollbacks == 0 and not session.added
    assert len(session.statements) == 4
    for statement in session.statements:
        sql = str(statement.compile(dialect=postgresql.dialect())).lower()
        assert "owner_user_id =" in sql
        assert "for update" not in sql


@pytest.mark.parametrize("entry", ("t2i", "t2v", "poll_t2v", "poll_i2v"))
async def test_execution_optional_null_links_are_allowed(entry):
    validate, _ = interface()
    job = execution_job(entry)
    session = ExecutionSession(job)
    assert await validate(session, job) is None
    assert session.statements == []


async def test_execution_new_i2v_requires_source():
    validate, error = interface()
    job = execution_job("i2v")
    with pytest.raises(error, match="^Content ownership reference validation failed\\.$"):
        await validate(ExecutionSession(job), job)


@pytest.mark.parametrize("entry", ENTRIES)
async def test_execution_terminal_noop_before_owner_or_effects(entry, monkeypatch):
    job = execution_job(entry, state=JobState.COMPLETED, owner_user_id=None)
    session = ExecutionSession(job)
    spies = effect_spies(monkeypatch)
    await getattr(handlers, "handle_" + entry.removeprefix("poll_"))(session, job)
    assert job.state == JobState.COMPLETED and session.commits == 0
    for spy in spies:
        spy.assert_not_called()


@pytest.mark.parametrize("attempt", ("image", "video", "i2v"))
async def test_execution_each_provider_attempt_rechecks_before_increment(attempt, monkeypatch):
    _, error = interface()
    job, session = linked_session("i2v" if attempt == "i2v" else "t2i")
    session.rows[job.enhancement_id].owner_user_id = FOREIGN
    spies = effect_spies(monkeypatch)
    with pytest.raises(error):
        if attempt == "image":
            await handlers._attempt_imagen_generation(session, job, number_of_images=1, aspect_ratio="1:1")
        elif attempt == "video":
            await handlers._attempt_veo_submit(session, job, aspect_ratio="1:1", duration_sec=4)
        else:
            await handlers._attempt_veo_i2v_submit(session, job, aspect_ratio="1:1", duration_sec=4,
                                                 image_bytes=b"fixture", image_mime="image/png")
    assert job.attempts == 0 and session.commits == 0
    for spy in spies:
        spy.assert_not_called()


@pytest.mark.parametrize("entry", ("t2i", "t2v", "i2v"))
async def test_execution_rollback_refetch_uses_cached_identifier(entry, monkeypatch):
    from sqlalchemy.orm import Session, make_transient_to_detached
    job, session = linked_session(entry)
    job_id, mode = job.id, job.mode
    orm = Session()
    async def rollback():
        make_transient_to_detached(job)
        orm.add(job)
        orm.expire(job, ["id", "mode"])
        session.rollbacks += 1
    async def get(model, value):
        from sqlalchemy.orm.attributes import set_committed_value
        assert value == job_id
        set_committed_value(job, "id", job_id)
        set_committed_value(job, "mode", mode)
        return job
    monkeypatch.setattr(session, "rollback", rollback)
    monkeypatch.setattr(session, "get", get)
    monkeypatch.setattr(handlers.rate_limit, "acquire", AsyncMock(side_effect=RuntimeError("fixed_failure")))
    monkeypatch.setattr(handlers.pipeline_link, "fail_blocked_children_for_parent", AsyncMock())
    try:
        await getattr(handlers, "handle_" + entry)(session, job)
        assert job.state == JobState.FAILED and session.rollbacks == 1
    finally:
        orm.close()


@pytest.mark.parametrize("entry", ("t2i", "t2v", "i2v"))
async def test_execution_nested_attempt_mismatch_is_not_provider_error_or_retried(entry, monkeypatch):
    job, session = linked_session(entry)
    spies = effect_spies(monkeypatch)
    async def change_after_entry(_model):
        session.rows[job.enhancement_id].owner_user_id = FOREIGN
        return 0
    monkeypatch.setattr(handlers.rate_limit,"acquire",change_after_entry)
    await getattr(handlers,"handle_" + entry)(session,job)
    assert job.error["code"] == "ownership_reference_mismatch" and job.error["retryable"] is False
    assert job.attempts == 0
    for spy in spies:
        spy.assert_not_called()


@pytest.mark.parametrize("entry", ("t2v", "i2v"))
async def test_execution_poll_rechecks_relations_after_successful_submit(entry, monkeypatch):
    job, session = linked_session(entry)
    poll = AsyncMock(side_effect=AssertionError("unexpected_poll"))
    save = Mock(side_effect=AssertionError("unexpected_save"))
    async def submit(*args, **kwargs):
        session.rows[job.enhancement_id].owner_user_id = FOREIGN
        return SimpleNamespace(name="mock-operation")
    monkeypatch.setattr(handlers.rate_limit,"acquire",AsyncMock(return_value=0))
    monkeypatch.setattr(handlers.storage,"read_bytes",Mock(return_value=b"fixture"))
    monkeypatch.setattr(handlers.storage,"save_bytes",save)
    monkeypatch.setattr(handlers.veo,"submit_video",submit)
    monkeypatch.setattr(handlers.veo,"poll_operation",poll)
    await getattr(handlers,"handle_"+entry)(session,job)
    assert job.error["code"] == "ownership_reference_mismatch"
    assert job.attempts == 1
    poll.assert_not_called()
    save.assert_not_called()
