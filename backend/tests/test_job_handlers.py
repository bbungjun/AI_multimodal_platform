from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.models import Asset, AssetKind, GenerationMode, Job, JobState, utc_now
from app.services.jobs import handlers
from app.services.vertex.errors import VertexOutputUnavailableError


class FakeHandlerSession:
    def __init__(self, job: Job, *, assets: list[Asset] | None = None) -> None:
        self.job = job
        self.assets_by_id = {asset.id: asset for asset in assets or []}
        self.added: list[object] = []
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1

    async def get(self, model: object, entity_id: object) -> object | None:
        if model is Job and entity_id == self.job.id:
            return self.job
        if model is Asset:
            return self.assets_by_id.get(entity_id)
        return None


def _t2i_job() -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=JobState.PENDING,
        prompt="A cinematic mountain village",
        blocked=False,
        attempts=0,
        parameters={"aspect_ratio": "16:9", "number_of_images": 2},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def _t2v_job() -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2V,
        model="veo-3.0-fast-generate-001",
        state=JobState.PENDING,
        prompt="A cinematic flyover of a mountain village",
        blocked=False,
        attempts=0,
        parameters={"aspect_ratio": "16:9", "duration_sec": 8},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def _source_image_asset() -> Asset:
    now = utc_now()
    return Asset(
        id=uuid4(),
        job_id=uuid4(),
        kind=AssetKind.IMAGE,
        local_path="source-job/source.png",
        mime="image/png",
        size_bytes=12,
        created_at=now,
    )


def _i2v_job(source_asset_id: object) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.I2V,
        model="veo-3.0-fast-generate-001",
        state=JobState.PENDING,
        prompt="Animate this village into a slow cinematic push-in",
        source_asset_id=source_asset_id,
        blocked=False,
        attempts=0,
        parameters={"aspect_ratio": "9:16", "duration_sec": 6},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


async def test_handle_t2i_generates_images_stores_assets_and_links_pipeline(
    monkeypatch,
):
    job = _t2i_job()
    session = FakeHandlerSession(job)
    saved_files: list[tuple[object, str, bytes]] = []
    linked_jobs: list[object] = []

    async def acquire_rate_limit(model: str) -> float:
        assert model == "imagen-4.0-fast-generate-001"
        return 0.25

    async def generate_image(
        model: str,
        prompt: str,
        *,
        number_of_images: int,
        aspect_ratio: str,
    ) -> list[bytes]:
        assert model == "imagen-4.0-fast-generate-001"
        assert prompt == "A cinematic mountain village"
        assert number_of_images == 2
        assert aspect_ratio == "16:9"
        return [b"image-one", b"image-two"]

    def save_bytes(job_id: object, filename: str, data: bytes) -> str:
        saved_files.append((job_id, filename, data))
        return f"{job_id}/{filename}"

    async def link_completed_parent(_session: object, linked_job: Job) -> None:
        assert _session is session
        linked_jobs.append(linked_job.id)

    async def fail_blocked_children_for_parent(*_args: object) -> None:
        raise AssertionError("happy path must not fail blocked children")

    monkeypatch.setattr(handlers.rate_limit, "acquire", acquire_rate_limit)
    monkeypatch.setattr(handlers.imagen, "generate_image", generate_image)
    monkeypatch.setattr(handlers.storage, "save_bytes", save_bytes)
    monkeypatch.setattr(
        handlers.pipeline_link,
        "link_completed_parent",
        link_completed_parent,
    )
    monkeypatch.setattr(
        handlers.pipeline_link,
        "fail_blocked_children_for_parent",
        fail_blocked_children_for_parent,
    )

    await handlers.handle_t2i(session, job)

    assert job.state == JobState.COMPLETED
    assert job.vertex_charged is True
    assert job.attempts == 1
    assert job.error is None
    assert [entry["state"] for entry in job.state_history] == [
        "queued",
        "generating",
        "downloading",
        "completed",
    ]
    assert job.state_history[0]["detail"] == {"runner": "direct-handler"}
    assert job.state_history[1]["detail"] == {"rate_limit_wait_sec": 0.25}
    assert job.state_history[2]["detail"] == {"image_count": 2}

    assert saved_files == [
        (job.id, "output.png", b"image-one"),
        (job.id, "output-2.png", b"image-two"),
    ]
    assert len(session.added) == 2
    assets = session.added
    assert all(isinstance(asset, Asset) for asset in assets)
    assert [asset.kind for asset in assets] == [AssetKind.IMAGE, AssetKind.IMAGE]
    assert [asset.local_path for asset in assets] == [
        f"{job.id}/output.png",
        f"{job.id}/output-2.png",
    ]
    assert [asset.mime for asset in assets] == ["image/png", "image/png"]
    assert [asset.size_bytes for asset in assets] == [9, 9]

    assert linked_jobs == [job.id]
    assert session.commit_count == 5
    assert session.rollback_count == 0


async def test_handle_t2i_vertex_failure_marks_job_failed_and_cascades(
    monkeypatch,
):
    job = _t2i_job()
    session = FakeHandlerSession(job)
    cascaded_jobs: list[object] = []

    async def acquire_rate_limit(_model: str) -> float:
        return 0.0

    async def generate_image(*_args: object, **_kwargs: object) -> list[bytes]:
        raise VertexOutputUnavailableError()

    def save_bytes(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("failed T2I job must not save assets")

    async def link_completed_parent(*_args: object) -> None:
        raise AssertionError("failed T2I job must not link pipeline children")

    async def fail_blocked_children_for_parent(
        _session: object,
        failed_job: Job,
    ) -> None:
        assert _session is session
        cascaded_jobs.append(failed_job.id)

    monkeypatch.setattr(handlers.rate_limit, "acquire", acquire_rate_limit)
    monkeypatch.setattr(handlers.imagen, "generate_image", generate_image)
    monkeypatch.setattr(handlers.storage, "save_bytes", save_bytes)
    monkeypatch.setattr(
        handlers.pipeline_link,
        "link_completed_parent",
        link_completed_parent,
    )
    monkeypatch.setattr(
        handlers.pipeline_link,
        "fail_blocked_children_for_parent",
        fail_blocked_children_for_parent,
    )

    await handlers.handle_t2i(session, job)

    assert job.state == JobState.FAILED
    assert job.vertex_charged is False
    assert job.attempts == 1
    assert session.added == []
    assert [entry["state"] for entry in job.state_history] == [
        "queued",
        "generating",
        "failed",
    ]
    assert job.state_history[-1]["detail"] == {"error": "vertex_output_unavailable"}
    assert job.error == {
        "code": "vertex_output_unavailable",
        "message": "Vertex AI did not return an output.",
        "retryable": False,
        "retry_count": 1,
        "last_attempt_at": job.error["last_attempt_at"],
    }
    assert cascaded_jobs == [job.id]
    assert session.commit_count == 4
    assert session.rollback_count == 1


async def test_handle_t2v_submits_polls_stores_video_asset(monkeypatch):
    job = _t2v_job()
    session = FakeHandlerSession(job)
    operation = SimpleNamespace(name="projects/demo/locations/us/operations/veo-123")
    saved_files: list[tuple[object, str, bytes]] = []
    polled_operations: list[object] = []

    async def acquire_rate_limit(model: str) -> float:
        assert model == "veo-3.0-fast-generate-001"
        return 0.5

    async def submit_video(
        model: str,
        prompt: str,
        *,
        aspect_ratio: str,
        duration_sec: int,
    ) -> object:
        assert model == "veo-3.0-fast-generate-001"
        assert prompt == "A cinematic flyover of a mountain village"
        assert aspect_ratio == "16:9"
        assert duration_sec == 8
        return operation

    async def poll_operation(submitted_operation: object) -> bytes:
        polled_operations.append(submitted_operation)
        return b"video-bytes"

    def save_bytes(job_id: object, filename: str, data: bytes) -> str:
        saved_files.append((job_id, filename, data))
        return f"{job_id}/{filename}"

    monkeypatch.setattr(handlers.rate_limit, "acquire", acquire_rate_limit)
    monkeypatch.setattr(handlers.veo, "submit_video", submit_video)
    monkeypatch.setattr(handlers.veo, "poll_operation", poll_operation)
    monkeypatch.setattr(handlers.storage, "save_bytes", save_bytes)

    await handlers.handle_t2v(session, job)

    assert job.state == JobState.COMPLETED
    assert job.vertex_operation_name == operation.name
    assert job.vertex_charged is True
    assert job.attempts == 1
    assert job.error is None
    assert [entry["state"] for entry in job.state_history] == [
        "queued",
        "generating",
        "polling",
        "downloading",
        "completed",
    ]
    assert job.state_history[0]["detail"] == {"runner": "direct-handler"}
    assert job.state_history[1]["detail"] == {"rate_limit_wait_sec": 0.5}
    assert job.state_history[2]["detail"] == {"operation_name": operation.name}
    assert job.state_history[3]["detail"] == {"size_bytes": 11}

    assert polled_operations == [operation]
    assert saved_files == [(job.id, "output.mp4", b"video-bytes")]
    assert len(session.added) == 1
    asset = session.added[0]
    assert isinstance(asset, Asset)
    assert asset.kind == AssetKind.VIDEO
    assert asset.local_path == f"{job.id}/output.mp4"
    assert asset.mime == "video/mp4"
    assert asset.size_bytes == 11
    assert asset.duration_sec == 8.0

    assert session.commit_count == 6
    assert session.rollback_count == 0


async def test_handle_t2v_resumes_polling_operation_by_name(monkeypatch):
    job = _t2v_job()
    job.state = JobState.POLLING
    job.vertex_operation_name = "projects/demo/locations/us/operations/veo-resume"
    job.attempts = 1
    session = FakeHandlerSession(job)
    saved_files: list[tuple[object, str, bytes]] = []
    polled_names: list[str] = []

    async def acquire_rate_limit(*_args: object) -> float:
        raise AssertionError("resumed polling job must not acquire rate limit")

    async def submit_video(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("resumed polling job must not submit a new operation")

    async def poll_operation_name(operation_name: str) -> bytes:
        polled_names.append(operation_name)
        return b"resumed-video"

    def save_bytes(job_id: object, filename: str, data: bytes) -> str:
        saved_files.append((job_id, filename, data))
        return f"{job_id}/{filename}"

    monkeypatch.setattr(handlers.rate_limit, "acquire", acquire_rate_limit)
    monkeypatch.setattr(handlers.veo, "submit_video", submit_video)
    monkeypatch.setattr(handlers.veo, "poll_operation_name", poll_operation_name)
    monkeypatch.setattr(handlers.storage, "save_bytes", save_bytes)

    await handlers.handle_t2v(session, job)

    assert job.state == JobState.COMPLETED
    assert job.vertex_operation_name == "projects/demo/locations/us/operations/veo-resume"
    assert job.vertex_charged is True
    assert job.attempts == 1
    assert job.error is None
    assert [entry["state"] for entry in job.state_history] == [
        "downloading",
        "completed",
    ]
    assert job.state_history[0]["detail"] == {"size_bytes": 13}

    assert polled_names == ["projects/demo/locations/us/operations/veo-resume"]
    assert saved_files == [(job.id, "output.mp4", b"resumed-video")]
    assert len(session.added) == 1
    asset = session.added[0]
    assert isinstance(asset, Asset)
    assert asset.kind == AssetKind.VIDEO
    assert asset.local_path == f"{job.id}/output.mp4"
    assert asset.mime == "video/mp4"
    assert asset.size_bytes == 13
    assert asset.duration_sec == 8.0

    assert session.commit_count == 2
    assert session.rollback_count == 0


async def test_handle_t2v_poll_timeout_marks_job_failed_with_operation_name(
    monkeypatch,
):
    job = _t2v_job()
    session = FakeHandlerSession(job)
    operation = SimpleNamespace(name="projects/demo/locations/us/operations/veo-timeout")
    polled_operations: list[object] = []

    async def acquire_rate_limit(_model: str) -> float:
        return 0.0

    async def submit_video(*_args: object, **_kwargs: object) -> object:
        return operation

    async def poll_operation(submitted_operation: object) -> bytes:
        polled_operations.append(submitted_operation)
        raise handlers.veo.VeoTimeoutError(operation.name)

    def save_bytes(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("timed out T2V job must not save assets")

    monkeypatch.setattr(handlers.rate_limit, "acquire", acquire_rate_limit)
    monkeypatch.setattr(handlers.veo, "submit_video", submit_video)
    monkeypatch.setattr(handlers.veo, "poll_operation", poll_operation)
    monkeypatch.setattr(handlers.storage, "save_bytes", save_bytes)

    await handlers.handle_t2v(session, job)

    assert job.state == JobState.FAILED
    assert job.vertex_operation_name == operation.name
    assert job.vertex_charged is False
    assert job.attempts == 1
    assert session.added == []
    assert [entry["state"] for entry in job.state_history] == [
        "queued",
        "generating",
        "polling",
        "failed",
    ]
    assert job.state_history[-1]["detail"] == {"error": "veo_timeout"}
    assert job.error == {
        "code": "veo_timeout",
        "message": "Veo generation timed out while polling.",
        "retryable": True,
        "operation_name": operation.name,
        "retry_count": 1,
        "last_attempt_at": job.error["last_attempt_at"],
    }

    assert polled_operations == [operation]
    assert session.commit_count == 5
    assert session.rollback_count == 1


async def test_handle_i2v_reads_source_image_submits_polls_stores_video_asset(
    monkeypatch,
):
    source_asset = _source_image_asset()
    job = _i2v_job(source_asset.id)
    session = FakeHandlerSession(job, assets=[source_asset])
    operation = SimpleNamespace(name="projects/demo/locations/us/operations/i2v-123")
    read_paths: list[str] = []
    saved_files: list[tuple[object, str, bytes]] = []
    polled_operations: list[object] = []

    async def acquire_rate_limit(model: str) -> float:
        assert model == "veo-3.0-fast-generate-001"
        return 0.75

    def read_bytes(local_path: str) -> bytes:
        read_paths.append(local_path)
        return b"source-image"

    async def submit_video(
        model: str,
        prompt: str,
        *,
        aspect_ratio: str,
        duration_sec: int,
        image_bytes: bytes,
        image_mime: str,
    ) -> object:
        assert model == "veo-3.0-fast-generate-001"
        assert prompt == "Animate this village into a slow cinematic push-in"
        assert aspect_ratio == "9:16"
        assert duration_sec == 6
        assert image_bytes == b"source-image"
        assert image_mime == "image/png"
        return operation

    async def poll_operation(submitted_operation: object) -> bytes:
        polled_operations.append(submitted_operation)
        return b"i2v-video"

    def save_bytes(job_id: object, filename: str, data: bytes) -> str:
        saved_files.append((job_id, filename, data))
        return f"{job_id}/{filename}"

    monkeypatch.setattr(handlers.rate_limit, "acquire", acquire_rate_limit)
    monkeypatch.setattr(handlers.storage, "read_bytes", read_bytes)
    monkeypatch.setattr(handlers.veo, "submit_video", submit_video)
    monkeypatch.setattr(handlers.veo, "poll_operation", poll_operation)
    monkeypatch.setattr(handlers.storage, "save_bytes", save_bytes)

    await handlers.handle_i2v(session, job)

    assert job.state == JobState.COMPLETED
    assert job.vertex_operation_name == operation.name
    assert job.vertex_charged is True
    assert job.attempts == 1
    assert job.error is None
    assert [entry["state"] for entry in job.state_history] == [
        "queued",
        "generating",
        "polling",
        "downloading",
        "completed",
    ]
    assert job.state_history[0]["detail"] == {"runner": "direct-handler"}
    assert job.state_history[1]["detail"] == {"rate_limit_wait_sec": 0.75}
    assert job.state_history[2]["detail"] == {"operation_name": operation.name}
    assert job.state_history[3]["detail"] == {"size_bytes": 9}

    assert read_paths == ["source-job/source.png"]
    assert polled_operations == [operation]
    assert saved_files == [(job.id, "output.mp4", b"i2v-video")]
    assert len(session.added) == 1
    asset = session.added[0]
    assert isinstance(asset, Asset)
    assert asset.kind == AssetKind.VIDEO
    assert asset.local_path == f"{job.id}/output.mp4"
    assert asset.mime == "video/mp4"
    assert asset.size_bytes == 9
    assert asset.duration_sec == 6.0

    assert session.commit_count == 6
    assert session.rollback_count == 0
