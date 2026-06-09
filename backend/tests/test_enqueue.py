from __future__ import annotations

import logging
from types import SimpleNamespace
from uuid import uuid4

from app.config import Settings
from app.models import GenerationMode, Job, JobState, utc_now
from app.services.jobs import enqueue


class FakeTask:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def apply_async(self, args=None, kwargs=None, **options):
        self.calls.append(
            {
                "args": tuple(args or ()),
                "kwargs": dict(kwargs or {}),
                "options": options,
            }
        )
        return SimpleNamespace(id="celery-task-123")


class FailingTask:
    def apply_async(self, *args: object, **kwargs: object):
        raise RuntimeError("broker unavailable")


def _job() -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=JobState.PENDING,
        prompt="A small cabin at sunrise",
        blocked=False,
        attempts=0,
        parameters={"aspect_ratio": "1:1"},
        state_history=[],
        error=None,
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


async def test_enqueue_process_job_sends_job_id_only():
    job_id = uuid4()
    task = FakeTask()

    result = await enqueue.dispatch_job(
        job_id,
        reason="generation_created",
        settings=Settings(_env_file=None, job_dispatch_mode="celery"),
        process_job_task=task,
    )

    assert result.ok is True
    assert result.enqueued is True
    assert result.mode == "celery"
    assert result.queue == "generation"
    assert result.task_id == "celery-task-123"
    assert result.error_code is None
    assert task.calls == [
        {
            "args": (str(job_id),),
            "kwargs": {},
            "options": {"queue": "generation"},
        }
    ]
    sent_repr = repr(task.calls)
    assert "prompt" not in sent_repr
    assert "parameters" not in sent_repr
    assert "source_asset_id" not in sent_repr


async def test_polling_dispatch_mode_is_noop():
    job_id = uuid4()
    task = FakeTask()

    result = await enqueue.dispatch_job(
        job_id,
        reason="generation_created",
        settings=Settings(_env_file=None, job_dispatch_mode="polling"),
        process_job_task=task,
    )

    assert result.ok is True
    assert result.enqueued is False
    assert result.mode == "polling"
    assert result.queue is None
    assert result.task_id is None
    assert task.calls == []


async def test_enqueue_failure_is_reported_without_mutating_job():
    job = _job()
    original_state = job.state
    original_attempts = job.attempts
    original_history = list(job.state_history)
    original_error = job.error

    result = await enqueue.dispatch_job(
        job.id,
        reason="generation_created",
        settings=Settings(_env_file=None, job_dispatch_mode="celery"),
        process_job_task=FailingTask(),
    )

    assert result.ok is False
    assert result.enqueued is False
    assert result.mode == "celery"
    assert result.queue == "generation"
    assert result.task_id is None
    assert result.error_code == "runtime_error"
    assert "broker unavailable" in (result.error or "")
    assert job.state == original_state
    assert job.attempts == original_attempts
    assert job.state_history == original_history
    assert job.error == original_error


async def test_dispatch_logs_structured_success_fields(caplog):
    job_id = uuid4()
    caplog.set_level(logging.INFO)

    await enqueue.dispatch_job(
        job_id,
        reason="generation_created",
        settings=Settings(_env_file=None, job_dispatch_mode="celery"),
        process_job_task=FakeTask(),
    )

    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "Job dispatch completed."
    )
    assert record.job_id == str(job_id)
    assert record.dispatch_reason == "generation_created"
    assert record.dispatch_mode == "celery"
    assert record.dispatch_queue == "generation"
    assert record.celery_task_id == "celery-task-123"
    assert record.dispatch_status == "enqueued"
