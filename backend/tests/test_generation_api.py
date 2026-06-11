from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.api import generations
from app.config import Settings
from app.main import app
from app.models import (
    Asset,
    AssetKind,
    GenerationMode,
    Job,
    JobState,
    OutboxEvent,
    OutboxEventStatus,
    PromptEnhancement,
    utc_now,
)
from app.services.jobs import outbox
from app.services.jobs.i2v_guard import ACTIVE_I2V_UNIQUE_INDEX_NAME
from app.services.vertex import storage as vertex_storage


class FakeScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self) -> list[object]:
        return self.rows


class FakeGenerationSession:
    def __init__(
        self,
        *,
        prompt_enhancement: PromptEnhancement | None = None,
        jobs: list[Job] | None = None,
        scalar_results: list[list[object]] | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.commit_count = 0
        self.commit_error = commit_error
        self.prompt_enhancement = prompt_enhancement
        self.jobs = jobs or []
        self.scalar_results = scalar_results
        self.scalar_statements: list[object] = []
        self.get_calls: list[tuple[object, object]] = []
        self.events: list[str] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)
        if isinstance(instance, Job):
            self.events.append("add_job")
        if isinstance(instance, OutboxEvent):
            self.events.append("add_outbox")

    async def delete(self, instance: object) -> None:
        self.deleted.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.events.append("rollback")

    async def get(self, model, entity_id, **_kwargs):
        self.get_calls.append((model, entity_id))
        if model is PromptEnhancement:
            return (
                self.prompt_enhancement
                if self.prompt_enhancement is not None
                and self.prompt_enhancement.id == entity_id
                else None
            )
        if model is Job:
            return next((job for job in self.jobs if job.id == entity_id), None)
        if model is Asset:
            for job in self.jobs:
                asset = next(
                    (asset for asset in getattr(job, "assets", []) if asset.id == entity_id),
                    None,
                )
                if asset is not None:
                    return asset
            return None
        raise AssertionError("Unexpected row fetch during generation create")

    async def scalars(self, *args, **_kwargs) -> FakeScalarsResult:
        if args:
            self.scalar_statements.append(args[0])
        if self.scalar_results is not None:
            rows = self.scalar_results.pop(0) if self.scalar_results else []
            return FakeScalarsResult(rows)
        return FakeScalarsResult(self.jobs)


class RoutingScalarGenerationSession(FakeGenerationSession):
    def __init__(
        self,
        *,
        locked_asset: Asset,
        active_jobs: list[Job] | None = None,
    ) -> None:
        super().__init__(jobs=[])
        self.locked_asset = locked_asset
        self.active_jobs = active_jobs or []

    async def get(self, model, entity_id, **kwargs):
        if model is Asset and entity_id == self.locked_asset.id:
            return self.locked_asset
        return await super().get(model, entity_id, **kwargs)

    async def scalars(self, *args, **_kwargs) -> FakeScalarsResult:
        if args:
            self.scalar_statements.append(args[0])
            sql = str(
                args[0].compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            ).lower()
            if "from assets" in sql:
                return FakeScalarsResult([self.locked_asset])
            if "from jobs" in sql:
                return FakeScalarsResult(self.active_jobs)
        return FakeScalarsResult([])


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


async def _post_retry(path: str, session: FakeGenerationSession):
    async def override_session() -> AsyncIterator[FakeGenerationSession]:
        yield session

    app.dependency_overrides[generations.get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post(path)
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


def _failed_mock_provider_job() -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=JobState.FAILED,
        prompt="a quiet desk lamp [[mock-fail:imagen]]",
        blocked=False,
        attempts=1,
        parameters={"aspect_ratio": "1:1", "number_of_images": 1},
        state_history=[
            {
                "state": "failed",
                "at": now.isoformat(),
                "detail": {"error": "mock_provider_failure"},
            }
        ],
        error={
            "code": "mock_provider_failure",
            "message": "Mock provider failure was requested.",
            "retryable": False,
            "retry_count": 1,
            "last_attempt_at": now.isoformat(),
        },
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def _failed_i2v_job(source_asset_id=None) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.I2V,
        model="veo-3.0-fast-generate-001",
        state=JobState.FAILED,
        prompt="animate the desk lamp",
        blocked=False,
        attempts=1,
        parameters={"aspect_ratio": "16:9", "duration_sec": 4},
        state_history=[{"state": "failed", "at": now.isoformat()}],
        error={"message": "source failed"},
        vertex_charged=False,
        source_asset_id=source_asset_id,
        created_at=now,
        updated_at=now,
    )


def _settings_for_data_dir(tmp_path):
    return Settings(data_dir=tmp_path)


def _added_jobs(session: FakeGenerationSession) -> list[Job]:
    return [instance for instance in session.added if isinstance(instance, Job)]


def _added_outbox_events(session: FakeGenerationSession) -> list[OutboxEvent]:
    return [
        instance
        for instance in session.added
        if isinstance(instance, OutboxEvent)
    ]


def _assert_job_dispatch_event(
    session: FakeGenerationSession,
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
    jobs = _added_jobs(session)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.mode == GenerationMode.T2I
    assert job.state == JobState.PENDING
    assert job.blocked is False
    _assert_job_dispatch_event(session, job=job, reason="generation_created")
    assert session.events == ["add_job", "add_outbox", "commit"]


async def test_create_generation_records_dispatch_outbox_event_before_commit(monkeypatch):
    session = FakeGenerationSession()

    async def fail_dispatch_job(*_args, **_kwargs):
        raise AssertionError("generation API must not dispatch directly")

    monkeypatch.setattr(generations, "dispatch_job", fail_dispatch_job, raising=False)

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "a quiet desk lamp",
            "model": "imagen-4.0-fast-generate-001",
        },
        session,
    )

    assert response.status_code == 201
    job = _added_jobs(session)[0]
    _assert_job_dispatch_event(session, job=job, reason="generation_created")
    assert session.events == ["add_job", "add_outbox", "commit"]


async def test_create_generation_does_not_depend_on_broker_availability(monkeypatch):
    session = FakeGenerationSession()

    async def fail_dispatch_job(job_id, *, reason):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(generations, "dispatch_job", fail_dispatch_job, raising=False)

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "a quiet desk lamp",
            "model": "imagen-4.0-fast-generate-001",
        },
        session,
    )

    assert response.status_code == 201
    job = _added_jobs(session)[0]
    assert job.state == JobState.PENDING
    assert job.attempts == 0
    assert job.state_history == []
    assert job.error is None
    assert session.commit_count == 1
    _assert_job_dispatch_event(session, job=job, reason="generation_created")
    assert session.events == ["add_job", "add_outbox", "commit"]


async def test_create_i2v_generation_rejects_active_job_for_same_source_asset():
    parent = _job_with_asset()
    source_asset = parent.assets[0]
    active_i2v = Job(
        id=uuid4(),
        mode=GenerationMode.I2V,
        model="veo-3.0-fast-generate-001",
        state=JobState.POLLING,
        prompt="animate the same desk lamp",
        source_asset_id=source_asset.id,
        parent_job_id=parent.id,
        blocked=False,
        attempts=1,
        parameters={"aspect_ratio": "16:9", "duration_sec": 4},
        state_history=[],
        error=None,
        vertex_charged=False,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session = FakeGenerationSession(
        jobs=[parent],
        scalar_results=[[source_asset], [active_i2v]],
    )

    response = await _post_generation(
        {
            "mode": "i2v",
            "prompt": "animate the desk lamp again",
            "model": "veo-3.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "duration_sec": 4,
            "source_asset_id": str(source_asset.id),
        },
        session,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "An active I2V generation already exists for this source asset."
    )
    assert _added_jobs(session) == []
    assert _added_outbox_events(session) == []
    assert session.commit_count == 0


async def test_create_i2v_generation_locks_source_asset_before_duplicate_check():
    parent = _job_with_asset()
    source_asset = parent.assets[0]
    session = RoutingScalarGenerationSession(locked_asset=source_asset)

    response = await _post_generation(
        {
            "mode": "i2v",
            "prompt": "animate the desk lamp",
            "model": "veo-3.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "duration_sec": 4,
            "source_asset_id": str(source_asset.id),
        },
        session,
    )

    assert response.status_code == 201
    assert len(session.scalar_statements) >= 2
    lock_sql = str(
        session.scalar_statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    active_check_sql = str(
        session.scalar_statements[1].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "from assets" in lock_sql
    assert "for update" in lock_sql
    assert "from jobs" in active_check_sql
    assert "jobs.mode = 'i2v'" in active_check_sql


async def test_create_i2v_generation_maps_unique_index_error_to_conflict():
    parent = _job_with_asset()
    source_asset = parent.assets[0]
    integrity_error = IntegrityError(
        statement="INSERT INTO jobs ...",
        params={},
        orig=Exception(ACTIVE_I2V_UNIQUE_INDEX_NAME),
    )
    session = FakeGenerationSession(
        jobs=[parent],
        scalar_results=[[source_asset], []],
        commit_error=integrity_error,
    )

    response = await _post_generation(
        {
            "mode": "i2v",
            "prompt": "animate the desk lamp",
            "model": "veo-3.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "duration_sec": 4,
            "source_asset_id": str(source_asset.id),
        },
        session,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "An active I2V generation already exists for this source asset."
    )
    assert "rollback" in session.events


async def test_create_t2i_generation_accepts_max_image_count_boundary():
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "a four panel image set",
            "model": "imagen-4.0-fast-generate-001",
            "aspect_ratio": "1:1",
            "number_of_images": 4,
        },
        session,
    )

    assert response.status_code == 201
    assert session.commit_count == 1
    job = _added_jobs(session)[0]
    assert job.parameters == {"aspect_ratio": "1:1", "number_of_images": 4}


async def test_create_t2v_generation_accepts_max_duration_boundary():
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "t2v",
            "prompt": "slow camera push toward the desk lamp",
            "model": "veo-3.0-fast-generate-001",
            "aspect_ratio": "16:9",
            "duration_sec": 8,
        },
        session,
    )

    assert response.status_code == 201
    assert session.commit_count == 1
    job = _added_jobs(session)[0]
    assert job.parameters == {"aspect_ratio": "16:9", "duration_sec": 8}


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {
                "mode": "t2i",
                "prompt": "invalid image count",
                "model": "imagen-4.0-fast-generate-001",
                "number_of_images": 0,
            },
            "number_of_images",
        ),
        (
            {
                "mode": "t2i",
                "prompt": "invalid image count",
                "model": "imagen-4.0-fast-generate-001",
                "number_of_images": 5,
            },
            "number_of_images",
        ),
        (
            {
                "mode": "t2v",
                "prompt": "invalid duration",
                "model": "veo-3.0-fast-generate-001",
                "duration_sec": 0,
            },
            "duration_sec",
        ),
        (
            {
                "mode": "t2v",
                "prompt": "invalid duration",
                "model": "veo-3.0-fast-generate-001",
                "duration_sec": 9,
            },
            "duration_sec",
        ),
        (
            {
                "mode": "t2i",
                "prompt": "invalid aspect ratio",
                "model": "imagen-4.0-fast-generate-001",
                "aspect_ratio": "x",
            },
            "aspect_ratio",
        ),
        (
            {
                "mode": "t2v",
                "prompt": "invalid aspect ratio",
                "model": "veo-3.0-fast-generate-001",
                "aspect_ratio": "12345678901234567",
            },
            "aspect_ratio",
        ),
    ],
)
async def test_create_generation_rejects_invalid_option_values_before_job_creation(
    payload: dict,
    field: str,
):
    session = FakeGenerationSession()

    response = await _post_generation(payload, session)

    assert response.status_code == 422
    assert any(error["loc"][-1] == field for error in response.json()["detail"])
    assert session.added == []
    assert session.commit_count == 0
    assert session.get_calls == []


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

    jobs = _added_jobs(session)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.prompt == "cinematic quiet desk lamp"
    assert job.enhanced_prompt == "cinematic quiet desk lamp"
    assert job.enhancement_id == enhancement_id
    _assert_job_dispatch_event(session, job=job, reason="generation_created")


async def test_create_generation_rejects_missing_prompt_enhancement_without_job():
    enhancement_id = uuid4()
    session = FakeGenerationSession()

    response = await _post_generation(
        {
            "mode": "t2i",
            "prompt": "cinematic quiet desk lamp",
            "model": "imagen-4.0-fast-generate-001",
            "enhancement_id": str(enhancement_id),
        },
        session,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Prompt enhancement was not found."
    assert session.get_calls == [(PromptEnhancement, enhancement_id)]
    assert session.added == []
    assert session.commit_count == 0


@pytest.mark.parametrize(
    ("target_mode", "target_model"),
    [
        (GenerationMode.T2V, "imagen-4.0-fast-generate-001"),
        (GenerationMode.T2I, "imagen-4.0-generate-001"),
    ],
)
async def test_create_generation_rejects_prompt_enhancement_target_mismatch_without_job(
    target_mode: GenerationMode,
    target_model: str,
):
    enhancement_id = uuid4()
    session = FakeGenerationSession(
        prompt_enhancement=PromptEnhancement(
            id=enhancement_id,
            original="desk lamp",
            enhanced="cinematic quiet desk lamp",
            components={"subject": "desk lamp"},
            target_mode=target_mode,
            target_model=target_model,
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

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Prompt enhancement target does not match generation request."
    )
    assert session.get_calls == [(PromptEnhancement, enhancement_id)]
    assert session.added == []
    assert session.commit_count == 0


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


async def test_get_generation_serializes_failed_job_error_contract():
    job = _failed_mock_provider_job()
    session = FakeGenerationSession(jobs=[job])

    response = await _get_generations(f"/api/generations/{job.id}", session)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(job.id)
    assert body["state"] == "failed"
    assert body["attempts"] == 1
    assert body["vertex_charged"] is False
    assert body["assets"] == []
    assert body["error"] == job.error


async def test_retry_failed_generation_creates_new_pending_job_without_mutating_original():
    source = _failed_mock_provider_job()
    source.enhanced_prompt = "cinematic quiet desk lamp"
    source.enhancement_id = uuid4()
    source.parent_job_id = uuid4()
    source.parameters = {"aspect_ratio": "1:1", "nested": {"style": "soft"}}
    session = FakeGenerationSession(jobs=[source])

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] != str(source.id)
    assert body["retry_of_job_id"] == str(source.id)
    assert body["mode"] == "t2i"
    assert body["model"] == source.model
    assert body["prompt"] == source.prompt
    assert body["enhanced_prompt"] == source.enhanced_prompt
    assert body["enhancement_id"] == str(source.enhancement_id)
    assert body["parent_job_id"] == str(source.parent_job_id)
    assert body["source_asset_id"] is None
    assert body["state"] == "pending"
    assert body["blocked"] is False
    assert body["vertex_operation_name"] is None
    assert body["attempts"] == 0
    assert body["state_history"] == []
    assert body["error"] is None
    assert body["vertex_charged"] is False
    assert body["assets"] == []

    assert source.state == JobState.FAILED
    assert source.attempts == 1
    assert source.error is not None
    retries = _added_jobs(session)
    assert len(retries) == 1
    retry = retries[0]
    assert retry.id != source.id
    assert retry.retry_of_job_id == source.id
    assert retry.state == JobState.PENDING
    assert retry.parameters == source.parameters
    assert retry.parameters is not source.parameters
    assert retry.state_history == []
    assert retry.error is None
    assert retry.assets == []
    assert session.commit_count == 1
    _assert_job_dispatch_event(session, job=retry, reason="generation_retry_created")


async def test_retry_generation_records_dispatch_outbox_event_before_commit(monkeypatch):
    source = _failed_mock_provider_job()
    session = FakeGenerationSession(jobs=[source])

    async def fail_dispatch_job(*_args, **_kwargs):
        raise AssertionError("retry API must not dispatch directly")

    monkeypatch.setattr(generations, "dispatch_job", fail_dispatch_job, raising=False)

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 201
    retry = _added_jobs(session)[0]
    _assert_job_dispatch_event(session, job=retry, reason="generation_retry_created")
    assert session.events == ["add_job", "add_outbox", "commit"]


async def test_retry_generation_returns_404_for_missing_job():
    response = await _post_retry(
        f"/api/generations/{uuid4()}/retry",
        FakeGenerationSession(jobs=[]),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Generation job was not found."


@pytest.mark.parametrize(
    "state",
    [
        JobState.PENDING,
        JobState.QUEUED,
        JobState.GENERATING,
        JobState.COMPLETED,
        JobState.CANCELLED,
    ],
)
async def test_retry_generation_rejects_non_failed_source_state(state: JobState):
    source = _failed_mock_provider_job()
    source.state = state
    session = FakeGenerationSession(jobs=[source])

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only failed generation jobs can be retried."
    assert session.added == []
    assert session.commit_count == 0


async def test_retry_i2v_rejects_missing_source_asset_without_job():
    source = _failed_i2v_job(source_asset_id=uuid4())
    session = FakeGenerationSession(jobs=[source])

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 409
    assert response.json()["detail"] == "Retry source asset is no longer available."
    assert session.added == []
    assert session.commit_count == 0


async def test_retry_i2v_rejects_detached_source_asset_without_job():
    source = _failed_i2v_job(source_asset_id=None)
    session = FakeGenerationSession(jobs=[source])

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 409
    assert response.json()["detail"] == "Retry source asset is no longer available."
    assert session.added == []
    assert session.commit_count == 0


async def test_retry_i2v_rejects_non_image_source_asset_without_job():
    parent = _job_with_video_asset()
    source = _failed_i2v_job(source_asset_id=parent.assets[0].id)
    session = FakeGenerationSession(jobs=[source, parent])

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 409
    assert response.json()["detail"] == "Retry source asset must be an image."
    assert session.added == []
    assert session.commit_count == 0


async def test_retry_i2v_copies_valid_source_asset_id():
    parent = _job_with_asset()
    source = _failed_i2v_job(source_asset_id=parent.assets[0].id)
    source.parent_job_id = parent.id
    session = FakeGenerationSession(jobs=[source, parent])

    response = await _post_retry(f"/api/generations/{source.id}/retry", session)

    assert response.status_code == 201
    body = response.json()
    assert body["retry_of_job_id"] == str(source.id)
    assert body["source_asset_id"] == str(parent.assets[0].id)
    assert body["parent_job_id"] == str(parent.id)
    retry = _added_jobs(session)[0]
    assert retry.source_asset_id == parent.assets[0].id
    assert retry.retry_of_job_id == source.id


async def test_retry_response_includes_retry_of_job_id():
    source = _failed_mock_provider_job()
    retry = _failed_mock_provider_job()
    retry.retry_of_job_id = source.id
    session = FakeGenerationSession(jobs=[retry])

    response = await _get_generations(f"/api/generations/{retry.id}", session)

    assert response.status_code == 200
    assert response.json()["retry_of_job_id"] == str(source.id)


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


async def test_delete_generation_rejects_active_source_asset_dependent_job(
    monkeypatch,
):
    parent = _job_with_asset()
    child = _job_with_asset()
    child.mode = GenerationMode.I2V
    child.model = "veo-3.0-fast-generate-001"
    child.state = JobState.PENDING
    child.parent_job_id = None
    child.source_asset_id = parent.assets[0].id
    child.assets = []
    session = FakeGenerationSession(jobs=[parent], scalar_results=[[], [child]])
    deleted_paths: list[str] = []

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda local_path, *, missing_ok: deleted_paths.append(local_path),
    )

    response = await _delete_generation(f"/api/generations/{parent.id}", session)

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Jobs with active dependent jobs cannot be deleted from History."
    )
    assert deleted_paths == []
    assert child.source_asset_id == parent.assets[0].id
    assert session.deleted == []
    assert session.commit_count == 0


async def test_delete_generation_rejects_active_retry_job(monkeypatch):
    source = _failed_mock_provider_job()
    retry = _failed_mock_provider_job()
    retry.state = JobState.PENDING
    retry.retry_of_job_id = source.id
    session = FakeGenerationSession(jobs=[source], scalar_results=[[], [retry]])

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("blocked delete must not touch storage")
        ),
    )

    response = await _delete_generation(f"/api/generations/{source.id}", session)

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Jobs with active dependent jobs cannot be deleted from History."
    )
    assert retry.retry_of_job_id == source.id
    assert session.deleted == []
    assert session.commit_count == 0


async def test_delete_generation_detaches_terminal_retry_job(monkeypatch):
    source = _failed_mock_provider_job()
    retry = _failed_mock_provider_job()
    retry.state = JobState.FAILED
    retry.retry_of_job_id = source.id
    session = FakeGenerationSession(jobs=[source], scalar_results=[[], [retry]])

    monkeypatch.setattr(
        generations.storage,
        "delete_file",
        lambda *_args, **_kwargs: None,
    )

    response = await _delete_generation(f"/api/generations/{source.id}", session)

    assert response.status_code == 204
    assert retry.retry_of_job_id is None
    assert session.deleted == [source]
    assert session.commit_count == 1


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
