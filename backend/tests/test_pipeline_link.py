from __future__ import annotations

from uuid import uuid4

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

    async def scalars(self, *_args, **_kwargs) -> FakeScalarsResult:
        rows = self.scalar_results.pop(0) if self.scalar_results else []
        return FakeScalarsResult(rows)

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1


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


async def test_link_completed_parent_fails_child_when_image_asset_missing():
    parent = _job(mode=GenerationMode.T2I, state=JobState.COMPLETED)
    child = _blocked_child(parent)
    session = FakePipelineLinkSession([[child], []])

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

    assert failed_count == 1
    assert blocked_child.state == JobState.FAILED
    assert blocked_child.error["code"] == pipeline_link.PIPELINE_PARENT_FAILED
    assert blocked_child.state_history[-1]["detail"] == {
        "error": pipeline_link.PIPELINE_PARENT_FAILED,
        "cause": "parent_failed",
    }
    assert unblocked_child.state == JobState.PENDING
    assert terminal_child.state == JobState.COMPLETED
    assert session.commit_count == 1
