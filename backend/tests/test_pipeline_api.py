from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx

from app.api import pipelines
from app.main import app
from app.models import Asset, AssetKind, GenerationMode, Job, JobState, utc_now


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
        self.added: list[Job] = []
        self.commit_count = 0
        self.jobs = {job.id: job for job in jobs or []}
        self.child_rows = child_rows or []

    def add_all(self, instances: list[Job]) -> None:
        self.added.extend(instances)
        self.jobs.update({job.id: job for job in instances})

    async def commit(self) -> None:
        self.commit_count += 1

    async def get(self, model, entity_id: UUID, **_kwargs) -> Job | None:
        if model is Job:
            return self.jobs.get(entity_id)
        raise AssertionError("Unexpected model lookup in pipeline test")

    async def scalars(self, *_args, **_kwargs) -> FakeScalarsResult:
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


async def test_create_pipeline_persists_parent_and_blocked_child():
    session = FakePipelineSession()

    response = await _post_pipeline(_pipeline_payload(), session)

    assert response.status_code == 201
    assert session.commit_count == 1
    assert len(session.added) == 2
    parent, child = session.added

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


async def test_create_pipeline_rejects_unsupported_image_model():
    session = FakePipelineSession()
    payload = _pipeline_payload() | {"image_model": "veo-3.0-fast-generate-001"}

    response = await _post_pipeline(payload, session)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Imagen model."
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
