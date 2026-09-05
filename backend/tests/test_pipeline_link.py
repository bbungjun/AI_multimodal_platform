from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.models import (
    Asset,
    AssetKind,
    GenerationMode,
    Job,
    JobState,
    OutboxEvent,
    OutboxEventStatus,
    utc_now,
)
from app.services.jobs import outbox
from app.services.jobs import pipeline_link


class FakeScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class FakePipelineLinkSession:
    def __init__(self, scalar_results: list[list[object]]) -> None:
        self.scalar_results = scalar_results
        self.commit_count = 0
        self.added: list[object] = []
        self.rollback_count = 0
        self.statements = []
        self.owner_status = "active"

    async def scalar(self, statement):
        return self.owner_status

    async def scalars(self, *_args, **_kwargs) -> FakeScalarsResult:
        self.statements.append(_args[0])
        rows = self.scalar_results.pop(0) if self.scalar_results else []
        return FakeScalarsResult(rows)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


def _job(
    *,
    mode: GenerationMode,
    state: JobState,
    blocked: bool = False,
    parent_job_id=None,
) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        owner_user_id=UUID(int=107),
        mode=mode,
        model=(
            "imagen-4.0-fast-generate-001"
            if mode == GenerationMode.T2I
            else "veo-3.0-fast-generate-001"
        ),
        state=state,
        prompt="prompt",
        parent_job_id=parent_job_id,
        blocked=blocked,
        attempts=0,
        parameters={},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def _image_asset(parent: Job) -> Asset:
    return Asset(
        id=uuid4(),
        job_id=parent.id,
        kind=AssetKind.IMAGE,
        local_path=f"{parent.id}/output.png",
        mime="image/png",
        size_bytes=12,
        created_at=utc_now(),
    )


def _video_asset(parent: Job) -> Asset:
    return Asset(
        id=uuid4(),
        job_id=parent.id,
        kind=AssetKind.VIDEO,
        local_path=f"{parent.id}/output.mp4",
        mime="video/mp4",
        size_bytes=12,
        created_at=utc_now(),
    )


def _blocked_child(parent: Job) -> Job:
    return _job(
        mode=GenerationMode.I2V,
        state=JobState.PENDING,
        blocked=True,
        parent_job_id=parent.id,
    )


def _added_outbox_events(session: FakePipelineLinkSession) -> list[OutboxEvent]:
    return [
        instance
        for instance in session.added
        if isinstance(instance, OutboxEvent)
    ]


def _assert_child_dispatch_event(
    session: FakePipelineLinkSession,
    *,
    child: Job,
) -> None:
    events = _added_outbox_events(session)
    assert len(events) == 1
    event = events[0]
    assert event.status == OutboxEventStatus.PENDING
    assert event.event_type == outbox.JOB_DISPATCH_REQUESTED
    assert event.aggregate_type == "job"
    assert event.aggregate_id == child.id
    assert event.payload == {
        "job_id": str(child.id),
        "reason": "pipeline_child_unblocked",
    }
    payload_repr = repr(event.payload)
    assert "prompt" not in payload_repr
    assert "parameters" not in payload_repr
    assert "source_asset_id" not in payload_repr


async def test_link_completed_parent_unblocks_child_with_image_asset():
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child = _blocked_child(parent)
    asset = _image_asset(parent)
    session = FakePipelineLinkSession([[child], [asset]])

    result = await pipeline_link.link_completed_parent(session, parent)

    assert result.linked is True
    assert result.child_id == child.id
    assert result.source_asset_id == asset.id
    assert child.source_asset_id == asset.id
    assert child.blocked is False
    assert child.state == JobState.PENDING
    _assert_child_dispatch_event(session, child=child)
    assert session.commit_count == 1


async def test_link_completed_parent_fails_child_when_image_asset_missing(monkeypatch):
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child = _blocked_child(parent)
    session = FakePipelineLinkSession([[child], []])
    terminal = []
    async def terminalize(*_args, **kwargs):
        terminal.append(kwargs)
    monkeypatch.setattr(pipeline_link.generation_credit, "terminalize_generation", terminalize)

    result = await pipeline_link.link_completed_parent(session, parent)

    assert result.linked is False
    assert result.reason == "source_asset_missing"
    assert result.child_id == child.id
    assert child.state == JobState.FAILED
    assert child.error["code"] == pipeline_link.PIPELINE_SOURCE_ASSET_MISSING
    assert child.state_history[-1]["detail"] == {
        "error": pipeline_link.PIPELINE_SOURCE_ASSET_MISSING
    }
    assert session.commit_count == 1
    assert terminal[0]["job"] is child and terminal[0]["succeeded"] is False
    assert terminal[0]["reason_code"] == "delivery_failed"


async def test_link_completed_parent_fails_child_when_asset_is_not_image():
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child = _blocked_child(parent)
    asset = _video_asset(parent)
    session = FakePipelineLinkSession([[child], [asset]])

    result = await pipeline_link.link_completed_parent(session, parent)

    assert result.linked is False
    assert result.reason == "source_asset_not_image"
    assert result.child_id == child.id
    assert child.state == JobState.FAILED
    assert child.error["code"] == pipeline_link.PIPELINE_SOURCE_ASSET_NOT_IMAGE
    assert session.commit_count == 1


async def test_link_completed_parent_skips_terminal_child():
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child = _job(
        mode=GenerationMode.I2V,
        state=JobState.COMPLETED,
        blocked=True,
        parent_job_id=parent.id,
    )
    session = FakePipelineLinkSession([[child]])

    result = await pipeline_link.link_completed_parent(session, parent)

    assert result.linked is False
    assert result.reason == "child_terminal"
    assert result.child_id == child.id
    assert child.source_asset_id is None
    assert child.blocked is True
    assert session.commit_count == 0


async def test_fail_blocked_children_for_parent_marks_only_blocked_active_children():
    parent = _job(mode=GenerationMode.T2I, state=JobState.FAILED)
    blocked_child = _blocked_child(parent)
    unblocked_child = _job(
        mode=GenerationMode.I2V,
        state=JobState.PENDING,
        blocked=False,
        parent_job_id=parent.id,
    )
    terminal_child = _job(
        mode=GenerationMode.I2V,
        state=JobState.COMPLETED,
        blocked=True,
        parent_job_id=parent.id,
    )
    session = FakePipelineLinkSession(
        [[blocked_child, unblocked_child, terminal_child]]
    )

    failed_count = await pipeline_link.fail_blocked_children_for_parent(
        session,
        parent,
    )

    assert getattr(failed_count, "failed_count", None) == 1
    assert blocked_child.state == JobState.FAILED
    assert blocked_child.error["code"] == pipeline_link.PIPELINE_PARENT_FAILED
    assert blocked_child.state_history[-1]["detail"] == {
        "error": pipeline_link.PIPELINE_PARENT_FAILED,
        "cause": "parent_failed",
    }
    assert unblocked_child.state == JobState.PENDING
    assert terminal_child.state == JobState.COMPLETED
    assert session.commit_count == 1


@pytest.mark.parametrize("corruption", ("foreign", "null_child", "null_parent", "wrong_parent", "wrong_asset"))
async def test_pipeline_execution_rejects_corrupt_relation_without_child_mutation(corruption):
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child, asset = _blocked_child(parent), _image_asset(parent)
    if corruption == "foreign":
        child.owner_user_id = UUID(int=108)
    elif corruption == "null_child":
        child.owner_user_id = None
    elif corruption == "null_parent":
        parent.owner_user_id = None
    elif corruption == "wrong_parent":
        child.parent_job_id = uuid4()
    else:
        asset.job_id = uuid4()
    session = FakePipelineLinkSession([[child], [asset]])
    result = await pipeline_link.link_completed_parent(session, parent)
    assert result.linked is False and result.reason == "ownership_reference_mismatch"
    assert result.child_id is None and result.source_asset_id is None
    assert child.blocked and child.source_asset_id is None and child.state == JobState.PENDING
    assert not session.added and session.commit_count == 0
    assert parent.state == JobState.COMPLETED


async def test_suspended_owner_cancels_child_instead_of_enqueuing(monkeypatch):
    from unittest.mock import AsyncMock
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child, asset = _blocked_child(parent), _image_asset(parent)
    session = FakePipelineLinkSession([[child], [asset]])
    session.owner_status = "suspended"
    terminal = AsyncMock()
    monkeypatch.setattr(pipeline_link.generation_credit, "terminalize_generation", terminal)
    result = await pipeline_link.link_completed_parent(session, parent)
    assert result.reason == "user_suspended" and not result.linked
    assert child.state == JobState.CANCELLED and not session.added
    assert terminal.call_args.kwargs["job"] is child
    assert terminal.call_args.kwargs["succeeded"] is False


async def test_pipeline_execution_repeated_link_adds_only_one_outbox_and_locks_child():
    from sqlalchemy.dialects import postgresql
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child, asset = _blocked_child(parent), _image_asset(parent)
    session = FakePipelineLinkSession([[child], [asset], [child], [asset]])
    first = await pipeline_link.link_completed_parent(session, parent)
    second = await pipeline_link.link_completed_parent(session, parent)
    assert first.linked and not second.linked and second.reason == "child_already_unblocked"
    assert len(_added_outbox_events(session)) == 1 and session.commit_count == 1
    assert "FOR UPDATE OF jobs" in str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert session.statements[0].get_execution_options()["populate_existing"]


async def test_pipeline_execution_commit_failure_safe_result_preserves_completed_parent(monkeypatch):
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child, asset = _blocked_child(parent), _image_asset(parent)
    session = FakePipelineLinkSession([[child], [asset]])
    async def fail_commit():
        raise RuntimeError("SECRET_CANARY")
    monkeypatch.setattr(session,"commit",fail_commit)
    result = await pipeline_link.link_completed_parent(session, parent)
    assert result.reason == "pipeline_link_failed" and not result.linked
    assert result.child_id is None and result.source_asset_id is None
    assert "SECRET_CANARY" not in repr(result)
    assert parent.state == JobState.COMPLETED and session.rollback_count == 1


async def test_pipeline_execution_failure_cascade_skips_foreign_and_null_children():
    parent = _job(mode=GenerationMode.T2I, state=JobState.FAILED)
    own, foreign, null_owner = (_blocked_child(parent) for _ in range(3))
    foreign.owner_user_id, null_owner.owner_user_id = UUID(int=108), None
    session = FakePipelineLinkSession([[own, foreign, null_owner]])
    result = await pipeline_link.fail_blocked_children_for_parent(session,parent)
    assert getattr(result,"failed_count",None) == 1
    assert result.skipped_count == 2 and result.reason == "ownership_reference_mismatch"
    assert own.state == JobState.FAILED
    assert foreign.state == null_owner.state == JobState.PENDING
    assert foreign.error is None and null_owner.error is None
