from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest

from app.api import generations
from app.config import Settings
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
from app.services.vertex import storage as vertex_storage


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
        scalar_results: list[list[Job]] | None = None,
    ) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commit_count = 0
        self.prompt_enhancement = prompt_enhancement
        self.jobs = jobs or []
        self.scalar_results = scalar_results
        self.scalar_statements: list[object] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def delete(self, instance: object) -> None:
        self.deleted.append(instance)

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

    async def scalars(self, *args, **_kwargs) -> FakeScalarsResult:
        if args:
            self.scalar_statements.append(args[0])
        if self.scalar_results is not None:
            rows = self.scalar_results.pop(0) if self.scalar_results else []
            return FakeScalarsResult(rows)
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


async def _delete_generation(path: str, session: FakeGenerationSession):
    async def override_session() -> AsyncIterator[FakeGenerationSession]:
        yield session

    app.dependency_overrides[generations.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.delete(path)
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


def _job_with_video_asset() -> Job:
    now = utc_now()
    job_id = uuid4()
    asset_id = uuid4()
    job = Job(
        id=job_id,
        mode=GenerationMode.T2V,
        model="veo-3.0-fast-generate-001",
        state=JobState.FAILED,
        prompt="slow camera push toward the desk lamp",
        blocked=False,
        attempts=2,
        parameters={"aspect_ratio": "16:9", "duration_sec": 8},
        state_history=[{"state": "failed", "at": now.isoformat()}],
        error={"message": "provider rejected request"},
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )
    job.assets = [
        Asset(
            id=asset_id,
            job_id=job_id,
            kind=AssetKind.VIDEO,
            local_path=f"{job_id}/output.mp4",
            mime="video/mp4",
            size_bytes=42,
            width=1280,
            height=720,
            duration_sec=8.0,
            created_at=now,
        )
    ]
    return job


def _settings_for_data_dir(tmp_path):
    return Settings(data_dir=tmp_path)


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


async def test_create_t2i_generation_rejects_veo_model_before_creating_job():
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "a quiet desk lamp",
            "model": "veo-3.0-fast-generate-001",
        },
        session,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Imagen model."
    assert session.added == []
    assert session.commit_count == 0


async def test_create_t2v_generation_rejects_imagen_model_before_creating_job():
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "t2v",
            "prompt": "slow camera push toward the desk lamp",
            "model": "imagen-4.0-fast-generate-001",
        },
        session,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Veo model."
    assert session.added == []
    assert session.commit_count == 0


async def test_create_i2v_generation_rejects_imagen_model_before_source_lookup():
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "i2v",
            "prompt": "animate the desk lamp",
            "model": "imagen-4.0-fast-generate-001",
            "source_asset_id": str(uuid4()),
        },
        session,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported Veo model."
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


async def test_list_generations_applies_combined_filters_and_pagination():
    job = _job_with_video_asset()
    session = FakeGenerationSession(scalar_results=[[job]])

    response = await _get_generations(
        "/api/generations"
        "?mode=t2v"
        "&asset_kind=video"
        "&model=veo-3.0-fast-generate-001"
        "&state=failed"
        "&limit=2"
        "&offset=1",
        session,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["mode"] == "t2v"
    assert body[0]["state"] == "failed"
    assert body[0]["model"] == "veo-3.0-fast-generate-001"
    assert body[0]["assets"][0]["kind"] == "video"
    assert body[0]["assets"][0]["url"] == f"/files/{job.id}/output.mp4"

    assert len(session.scalar_statements) == 1
    statement = session.scalar_statements[0]
    compiled = statement.compile(compile_kwargs={"literal_binds": False})
    sql = str(compiled)
    assert "jobs.mode" in sql
    assert "assets.kind" in sql
    assert "jobs.model" in sql
    assert "jobs.state" in sql
    assert "ORDER BY jobs.created_at DESC" in sql
    assert "LIMIT" in sql
    assert "OFFSET" in sql
    param_values = list(compiled.params.values())
    assert GenerationMode.T2V in param_values
    assert AssetKind.VIDEO in param_values
    assert JobState.FAILED in param_values
    assert "veo-3.0-fast-generate-001" in param_values
    assert 2 in param_values
    assert 1 in param_values


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("asset_kind=audio", "asset_kind"),
        ("limit=0", "limit"),
        ("limit=101", "limit"),
        ("offset=-1", "offset"),
    ],
)
async def test_list_generations_rejects_invalid_query_values_before_db(
    query: str,
    field: str,
):
    session = FakeGenerationSession()

    response = await _get_generations(f"/api/generations?{query}", session)

    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])
    assert session.scalar_statements == []


async def test_delete_terminal_generation_removes_asset_and_job(monkeypatch):
    job = _job_with_asset()
    session = FakeGenerationSession(jobs=[job], scalar_results=[[], []])
    deleted_paths: list[str] = []

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda local_path, *, missing_ok: deleted_paths.append(local_path),
    )

    response = await _delete_generation(f"/api/generations/{job.id}", session)

    assert response.status_code == 204
    assert response.content == b""
    assert deleted_paths == [f"{job.id}/output.png"]
    assert session.deleted == [job]
    assert session.commit_count == 1


async def test_delete_generation_tolerates_missing_asset_file(monkeypatch, tmp_path):
    job = _job_with_asset()
    session = FakeGenerationSession(jobs=[job], scalar_results=[[], []])
    monkeypatch.setattr(
        vertex_storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )

    response = await _delete_generation(f"/api/generations/{job.id}", session)

    assert response.status_code == 204
    assert session.deleted == [job]
    assert session.commit_count == 1


async def test_delete_generation_rejects_unsafe_asset_path_without_deleting_job(
    monkeypatch,
    tmp_path,
):
    job = _job_with_asset()
    job.assets[0].local_path = f"{job.id}/../secret.txt"
    session = FakeGenerationSession(jobs=[job], scalar_results=[[], []])
    monkeypatch.setattr(
        vertex_storage,
        "get_settings",
        lambda: _settings_for_data_dir(tmp_path),
    )

    response = await _delete_generation(f"/api/generations/{job.id}", session)

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Generation asset file path is unsafe; job was not deleted."
    )
    assert session.deleted == []
    assert session.commit_count == 0


async def test_delete_generation_rejects_non_terminal_job(monkeypatch):
    job = _job_with_asset()
    job.state = JobState.PENDING
    session = FakeGenerationSession(jobs=[job])

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("non-terminal delete must not touch storage")
        ),
    )

    response = await _delete_generation(f"/api/generations/{job.id}", session)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only terminal jobs can be deleted from History."
    assert session.deleted == []
    assert session.commit_count == 0


async def test_delete_generation_rejects_active_dependent_job(monkeypatch):
    parent = _job_with_asset()
    child = _job_with_asset()
    child.state = JobState.PENDING
    child.parent_job_id = parent.id
    session = FakeGenerationSession(jobs=[parent], scalar_results=[[child], []])

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("blocked delete must not touch storage")
        ),
    )

    response = await _delete_generation(f"/api/generations/{parent.id}", session)

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Jobs with active dependent jobs cannot be deleted from History."
    )
    assert session.deleted == []
    assert session.commit_count == 0


async def test_delete_generation_detaches_terminal_dependent_job(monkeypatch):
    parent = _job_with_asset()
    child = _job_with_asset()
    child.state = JobState.COMPLETED
    child.parent_job_id = parent.id
    child.source_asset_id = parent.assets[0].id
    session = FakeGenerationSession(jobs=[parent], scalar_results=[[child], [child]])
    deleted_paths: list[str] = []

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda local_path, *, missing_ok: deleted_paths.append(local_path),
    )

    response = await _delete_generation(f"/api/generations/{parent.id}", session)

    assert response.status_code == 204
    assert deleted_paths == [f"{parent.id}/output.png"]
    assert child.parent_job_id is None
    assert child.source_asset_id is None
    assert session.deleted == [parent]
    assert session.commit_count == 1
