from __future__ import annotations

from uuid import uuid4

from app.models import Asset, AssetKind, GenerationMode, Job, JobState, utc_now
from app.services.jobs import handlers


class FakeHandlerSession:
    def __init__(self, job: Job) -> None:
        self.job = job
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
