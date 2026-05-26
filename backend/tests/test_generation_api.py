from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx

from app.api import generations
from app.main import app
from app.models import (
    Asset,
    AssetKind,
    GenerationMode,
    Job,
    JobState,
    PromptEnhancement,
    utc_now,
)


class FakeScalarsResult:
    def __init__(self, rows: list[Job]) -> None:
        self.rows = rows

    def all(self) -> list[Job]:
        return self.rows


class FakeGenerationSession:
    def __init__(
        self,
        *,
        prompt_enhancement: PromptEnhancement | None = None,
        jobs: list[Job] | None = None,
    ) -> None:
        self.added: list[object] = []
        self.commit_count = 0
        self.prompt_enhancement = prompt_enhancement
        self.jobs = jobs or []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1

    async def get(self, model, entity_id, **_kwargs):
        if model is PromptEnhancement:
            return (
                self.prompt_enhancement
                if self.prompt_enhancement is not None
                and self.prompt_enhancement.id == entity_id
                else None
            )
        if model is Job:
            return next((job for job in self.jobs if job.id == entity_id), None)
        raise AssertionError("Unexpected row fetch during generation create")

    async def scalars(self, *_args, **_kwargs) -> FakeScalarsResult:
        return FakeScalarsResult(self.jobs)


async def _post_generation(payload: dict, session: FakeGenerationSession):
    async def override_session() -> AsyncIterator[FakeGenerationSession]:
        yield session

    app.dependency_overrides[generations.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post("/api/generations", json=payload)
    finally:
        app.dependency_overrides.pop(generations.get_session, None)


async def _get_generations(path: str, session: FakeGenerationSession):
    async def override_session() -> AsyncIterator[FakeGenerationSession]:
        yield session

    app.dependency_overrides[generations.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.pop(generations.get_session, None)


def _job_with_asset() -> Job:
    now = utc_now()
    job_id = uuid4()
    asset_id = uuid4()
    job = Job(
        id=job_id,
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=JobState.COMPLETED,
        prompt="a quiet desk lamp",
        blocked=False,
        attempts=1,
        parameters={"aspect_ratio": "1:1", "number_of_images": 1},
        state_history=[{"state": "completed", "at": now.isoformat()}],
        vertex_charged=True,
        created_at=now,
        updated_at=now,
    )
    job.assets = [
        Asset(
            id=asset_id,
            job_id=job_id,
            kind=AssetKind.IMAGE,
            local_path=f"{job_id}/output.png",
            mime="image/png",
            size_bytes=12,
            width=512,
            height=512,
            created_at=now,
        )
    ]
    return job


async def test_create_t2i_generation_persists_pending_job_without_vertex_call(monkeypatch):
    session = FakeGenerationSession()

    def fail_vertex_call(*_args, **_kwargs):
        raise AssertionError("Generation creation must not call Vertex")

    monkeypatch.setattr(generations, "get_vertex_client", fail_vertex_call, raising=False)
    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "a quiet desk lamp",
            "model": "imagen-4.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "number_of_images": 2,
        },
        session,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "t2i"
    assert body["state"] == "pending"
    assert body["prompt"] == "a quiet desk lamp"
    assert body["model"] == "imagen-4.0-fast-generate-001"
    assert body["parameters"] == {
        "aspect_ratio": "16:9",
        "number_of_images": 2,
    }
    assert body["assets"] == []
    assert body["vertex_charged"] is False

    assert session.commit_count == 1
    assert len(session.added) == 1
    job = session.added[0]
    assert isinstance(job, Job)
    assert job.mode == GenerationMode.T2I
    assert job.state == JobState.PENDING
    assert job.blocked is False


async def test_create_generation_rejects_auto_enhance_before_creating_job():
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "a quiet desk lamp",
            "model": "imagen-4.0-fast-generate-001",
            "auto_enhance": True,
        },
        session,
    )

    assert response.status_code == 501
    assert session.added == []
    assert session.commit_count == 0


async def test_create_generation_links_matching_prompt_enhancement():
    enhancement_id = uuid4()
    session = FakeGenerationSession(
        prompt_enhancement=PromptEnhancement(
            id=enhancement_id,
            original="desk lamp",
            enhanced="cinematic quiet desk lamp",
            components={"subject": "desk lamp"},
            target_mode=GenerationMode.T2I,
            target_model="imagen-4.0-fast-generate-001",
            llm_model="gemini-2.5-flash",
        )
    )

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "cinematic quiet desk lamp",
            "model": "imagen-4.0-fast-generate-001",
            "enhancement_id": str(enhancement_id),
        },
        session,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["prompt"] == "cinematic quiet desk lamp"
    assert body["enhanced_prompt"] == "cinematic quiet desk lamp"
    assert body["enhancement_id"] == str(enhancement_id)

    assert len(session.added) == 1
    job = session.added[0]
    assert isinstance(job, Job)
    assert job.prompt == "cinematic quiet desk lamp"
    assert job.enhanced_prompt == "cinematic quiet desk lamp"
    assert job.enhancement_id == enhancement_id


async def test_get_generation_returns_job_with_asset_dto():
    job = _job_with_asset()
    session = FakeGenerationSession(jobs=[job])

    response = await _get_generations(f"/api/generations/{job.id}", session)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(job.id)
    assert body["state"] == "completed"
    assert body["assets"] == [
        {
            "id": str(job.assets[0].id),
            "job_id": str(job.id),
            "kind": "image",
            "local_path": f"{job.id}/output.png",
            "mime": "image/png",
            "size_bytes": 12,
            "width": 512,
            "height": 512,
            "duration_sec": None,
            "created_at": job.assets[0].created_at.isoformat().replace("+00:00", "Z"),
            "url": f"/files/{job.id}/output.png",
        }
    ]


async def test_get_generation_returns_404_for_missing_job():
    response = await _get_generations(
        f"/api/generations/{uuid4()}",
        FakeGenerationSession(jobs=[]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Generation job was not found."


async def test_list_generations_returns_jobs_with_asset_dtos():
    job = _job_with_asset()
    session = FakeGenerationSession(jobs=[job])

    response = await _get_generations("/api/generations", session)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(job.id)
    assert body[0]["assets"][0]["url"] == f"/files/{job.id}/output.png"
