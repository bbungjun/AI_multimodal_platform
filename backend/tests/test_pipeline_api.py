from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest

from app.api import pipelines
from app.main import app
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


class FakeScalarsResult:
    def __init__(self, rows: list[Job]) -> None:
        self.rows = rows

    def first(self) -> Job | None:
        return self.rows[0] if self.rows else None


class FakePipelineSession:
    def __init__(
        self,
        *,
        jobs: list[Job] | None = None,
        child_rows: list[Job] | None = None,
    ) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.jobs = {job.id: job for job in jobs or []}
        self.child_rows = child_rows or []
        self.get_calls: list[tuple[object, UUID]] = []
        self.scalar_statements: list[object] = []
        self.events: list[str] = []

    def add_all(self, instances: list[Job]) -> None:
        self.added.extend(instances)
        self.jobs.update({job.id: job for job in instances})
        self.events.append("add_jobs")

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, OutboxEvent):
            self.events.append("add_outbox")

    async def commit(self) -> None:
        self.commit_count += 1
        self.events.append("commit")

    async def get(self, model, entity_id: UUID, **_kwargs) -> Job | None:
        self.get_calls.append((model, entity_id))
        if model is Job:
            return self.jobs.get(entity_id)
        raise AssertionError("Unexpected model lookup in pipeline test")

    async def scalars(self, *args, **_kwargs) -> FakeScalarsResult:
        if args:
            self.scalar_statements.append(args[0])
        return FakeScalarsResult(self.child_rows)


async def _post_pipeline(payload: dict, session: FakePipelineSession):
    async def override_session() -> AsyncIterator[FakePipelineSession]:
        yield session

    app.dependency_overrides[pipelines.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post("/api/pipelines", json=payload)
    finally:
        app.dependency_overrides.pop(pipelines.get_session, None)


async def _get_pipeline(path: str, session: FakePipelineSession):
    async def override_session() -> AsyncIterator[FakePipelineSession]:
        yield session

    app.dependency_overrides[pipelines.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.pop(pipelines.get_session, None)


def _pipeline_payload() -> dict:
    return {
        "image_prompt": "a quiet desk lamp",
        "video_prompt": "slow camera push toward the desk lamp",
        "image_model": "imagen-4.0-fast-generate-001",
        "video_model": "veo-3.0-fast-generate-001",
        "image_aspect_ratio": "1:1",
        "video_aspect_ratio": "16:9",
        "duration_sec": 4,
    }


def _job(
    *,
    mode: GenerationMode,
    model: str,
    prompt: str,
    state: JobState = JobState.PENDING,
    blocked: bool = False,
    parent_job_id: UUID | None = None,
    source_asset_id: UUID | None = None,
) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=mode,
        model=model,
        state=state,
        prompt=prompt,
        parent_job_id=parent_job_id,
        source_asset_id=source_asset_id,
        blocked=blocked,
        attempts=0,
        parameters={},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def _parent_with_asset() -> Job:
    parent = _job(
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        prompt="a quiet desk lamp",
        state=JobState.COMPLETED,
    )
    now = utc_now()
    parent.assets = [
        Asset(
            id=uuid4(),
            job_id=parent.id,
            kind=AssetKind.IMAGE,
            local_path=f"{parent.id}/output.png",
            mime="image/png",
            size_bytes=12,
            created_at=now,
        )
    ]
    return parent


def _added_jobs(session: FakePipelineSession) -> list[Job]:
    return [instance for instance in session.added if isinstance(instance, Job)]


def _added_outbox_events(session: FakePipelineSession) -> list[OutboxEvent]:
    return [
        instance
        for instance in session.added
        if isinstance(instance, OutboxEvent)
    ]


def _assert_job_dispatch_event(
    session: FakePipelineSession,
    *,
    job: Job,
    reason: str,
) -> OutboxEvent:
    events = _added_outbox_events(session)
    assert len(events) == 1
    event = events[0]
    assert event.status == OutboxEventStatus.PENDING
    assert event.event_type == outbox.JOB_DISPATCH_REQUESTED
    assert event.aggregate_type == "job"
    assert event.aggregate_id == job.id
    assert event.payload == {
        "job_id": str(job.id),
        "reason": reason,
    }
    payload_repr = repr(event.payload)
    assert "prompt" not in payload_repr
    assert "parameters" not in payload_repr
    assert "source_asset_id" not in payload_repr
    return event


async def test_create_pipeline_persists_parent_and_blocked_child():
    session = FakePipelineSession()

    response = await _post_pipeline(_pipeline_payload(), session)

    assert response.status_code == 201
    assert session.commit_count == 1
    jobs = _added_jobs(session)
    assert len(jobs) == 2
    parent, child = jobs

    assert parent.mode == GenerationMode.T2I
    assert parent.state == JobState.PENDING
    assert parent.blocked is False
    assert parent.prompt == "a quiet desk lamp"
    assert parent.parameters == {"aspect_ratio": "1:1", "number_of_images": 1}

    assert child.mode == GenerationMode.I2V
    assert child.state == JobState.PENDING
    assert child.blocked is True
    assert child.parent_job_id == parent.id
    assert child.source_asset_id is None
    assert child.parameters == {"aspect_ratio": "16:9", "duration_sec": 4}

    body = response.json()
    assert body["id"] == str(parent.id)
    assert body["parent"]["id"] == str(parent.id)
    assert body["child"]["id"] == str(child.id)
    assert body["child"]["parent_job_id"] == str(parent.id)
    assert body["child"]["blocked"] is True
    _assert_job_dispatch_event(session, job=parent, reason="pipeline_parent_created")
    assert session.events == ["add_jobs", "add_outbox", "commit"]


async def test_create_pipeline_records_parent_outbox_event_only(monkeypatch):
    session = FakePipelineSession()

    async def fail_dispatch_job(*_args, **_kwargs):
        raise AssertionError("pipeline API must not dispatch directly")

    monkeypatch.setattr(pipelines, "dispatch_job", fail_dispatch_job, raising=False)

    response = await _post_pipeline(_pipeline_payload(), session)

    assert response.status_code == 201
    parent, child = _added_jobs(session)
    _assert_job_dispatch_event(session, job=parent, reason="pipeline_parent_created")
    assert child.id not in [event.aggregate_id for event in _added_outbox_events(session)]
    assert child.blocked is True
    assert child.state == JobState.PENDING
    assert session.events == ["add_jobs", "add_outbox", "commit"]


async def test_create_pipeline_accepts_max_duration_boundary():
    session = FakePipelineSession()
    payload = _pipeline_payload() | {"duration_sec": 8}

    response = await _post_pipeline(payload, session)

    assert response.status_code == 201
    assert session.commit_count == 1
    jobs = _added_jobs(session)
    assert len(jobs) == 2
    parent, child = jobs
    assert parent.parameters == {"aspect_ratio": "1:1", "number_of_images": 1}
    assert child.parameters == {"aspect_ratio": "16:9", "duration_sec": 8}


@pytest.mark.parametrize(
    ("payload_overrides", "field"),
    [
        ({"duration_sec": 0}, "duration_sec"),
        ({"duration_sec": 9}, "duration_sec"),
        ({"image_aspect_ratio": "x"}, "image_aspect_ratio"),
        ({"image_aspect_ratio": "12345678901234567"}, "image_aspect_ratio"),
        ({"video_aspect_ratio": "x"}, "video_aspect_ratio"),
        ({"video_aspect_ratio": "12345678901234567"}, "video_aspect_ratio"),
    ],
)
async def test_create_pipeline_rejects_invalid_option_values_before_jobs(
    payload_overrides: dict,
    field: str,
):
    session = FakePipelineSession()

    response = await _post_pipeline(_pipeline_payload() | payload_overrides, session)

    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])
    assert session.added == []
    assert session.commit_count == 0


async def test_create_pipeline_rejects_unsupported_image_model():
    session = FakePipelineSession()
    payload = _pipeline_payload() | {"image_model": "veo-3.0-fast-generate-001"}

    response = await _post_pipeline(payload, session)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Imagen model."
    assert session.added == []
    assert session.commit_count == 0


async def test_create_pipeline_rejects_unsupported_video_model():
    session = FakePipelineSession()
    payload = _pipeline_payload() | {"video_model": "imagen-4.0-fast-generate-001"}

    response = await _post_pipeline(payload, session)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Veo model."
    assert session.added == []
    assert session.commit_count == 0


async def test_get_pipeline_returns_parent_and_child_with_assets():
    parent = _parent_with_asset()
    child = _job(
        mode=GenerationMode.I2V,
        model="veo-3.0-fast-generate-001",
        prompt="slow camera push toward the desk lamp",
        blocked=False,
        parent_job_id=parent.id,
        source_asset_id=parent.assets[0].id,
    )
    child.assets = []
    session = FakePipelineSession(jobs=[parent], child_rows=[child])

    response = await _get_pipeline(f"/api/pipelines/{parent.id}", session)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(parent.id)
    assert body["parent"]["assets"][0]["url"] == f"/files/{parent.id}/output.png"
    assert body["child"]["parent_job_id"] == str(parent.id)
    assert body["child"]["source_asset_id"] == str(parent.assets[0].id)
    assert body["child"]["blocked"] is False


async def test_get_pipeline_queries_i2v_child_by_parent_with_stable_ordering():
    parent = _parent_with_asset()
    child = _job(
        mode=GenerationMode.I2V,
        model="veo-3.0-fast-generate-001",
        prompt="slow camera push toward the desk lamp",
        blocked=True,
        parent_job_id=parent.id,
    )
    session = FakePipelineSession(jobs=[parent], child_rows=[child])

    response = await _get_pipeline(f"/api/pipelines/{parent.id}", session)

    assert response.status_code == 200
    assert response.json()["child"]["id"] == str(child.id)
    assert session.get_calls == [(Job, parent.id)]
    assert len(session.scalar_statements) == 1

    compiled = session.scalar_statements[0].compile(
        compile_kwargs={"literal_binds": False},
    )
    sql = str(compiled)
    assert "jobs.parent_job_id" in sql
    assert "jobs.mode" in sql
    assert "ORDER BY jobs.created_at, jobs.id" in sql
    param_values = list(compiled.params.values())
    assert parent.id in param_values
    assert GenerationMode.I2V in param_values


async def test_get_pipeline_rejects_invalid_parent_id_before_db_lookup():
    session = FakePipelineSession()

    response = await _get_pipeline("/api/pipelines/not-a-uuid", session)

    assert response.status_code == 422
    assert any(
        error["loc"][-1] == "parent_job_id"
        for error in response.json()["detail"]
    )
    assert session.get_calls == []
    assert session.scalar_statements == []


async def test_get_pipeline_returns_404_for_missing_parent():
    response = await _get_pipeline(
        f"/api/pipelines/{uuid4()}",
        FakePipelineSession(),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Pipeline parent job was not found."


async def test_get_pipeline_returns_404_for_missing_child():
    parent = _parent_with_asset()

    response = await _get_pipeline(
        f"/api/pipelines/{parent.id}",
        FakePipelineSession(jobs=[parent], child_rows=[]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Pipeline child job was not found."
