from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.config import Settings
from app.models import GenerationMode, Job, JobState, OutboxEventStatus, utc_now
from app.services.ops import metrics


class FakeExecuteResult:
    def __init__(self, *, rows: list[tuple[object, int]] | None = None, scalar=None):
        self.rows = rows or []
        self.scalar = scalar

    def all(self) -> list[tuple[object, int]]:
        return self.rows

    def scalar_one(self):
        return self.scalar


class FakeScalarsResult:
    def __init__(self, rows: list[Job]) -> None:
        self.rows = rows

    def all(self) -> list[Job]:
        return self.rows


class FakeOpsSession:
    def __init__(
        self,
        *,
        execute_results: list[FakeExecuteResult],
        failed_jobs: list[Job],
    ) -> None:
        self.execute_results = execute_results
        self.failed_jobs = failed_jobs
        self.execute_statements: list[object] = []
        self.scalar_statements: list[object] = []

    async def execute(self, statement: object) -> FakeExecuteResult:
        self.execute_statements.append(statement)
        return self.execute_results.pop(0)

    async def scalars(self, statement: object) -> FakeScalarsResult:
        self.scalar_statements.append(statement)
        return FakeScalarsResult(self.failed_jobs)


def _failed_job() -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2V,
        model="veo-3.0-fast-generate-001",
        state=JobState.FAILED,
        prompt="video prompt",
        blocked=False,
        attempts=3,
        parameters={"duration_sec": 4},
        state_history=[],
        error={
            "code": "veo_timeout",
            "message": "Veo generation timed out while polling.",
            "retryable": True,
            "dead_letter": True,
        },
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


async def test_collect_ops_health_counts_jobs_outbox_and_recent_failures():
    failed_job = _failed_job()
    session = FakeOpsSession(
        execute_results=[
            FakeExecuteResult(
                rows=[
                    (JobState.PENDING, 2),
                    (JobState.POLLING, 1),
                    (JobState.FAILED, 1),
                ],
            ),
            FakeExecuteResult(
                rows=[
                    (OutboxEventStatus.PENDING, 3),
                    (OutboxEventStatus.FAILED, 1),
                ],
            ),
            FakeExecuteResult(scalar=1),
            FakeExecuteResult(scalar=2),
        ],
        failed_jobs=[failed_job],
    )

    response = await metrics.collect_ops_health(
        session,
        settings=Settings(
            _env_file=None,
            job_dispatch_mode="celery",
            celery_default_queue="generation",
        ),
    )

    assert response.ok is True
    assert response.db == "up"
    assert response.dispatch.mode == "celery"
    assert response.dispatch.queue == "generation"
    assert response.dispatch.task_acks_late is True
    assert response.jobs.total == 4
    assert response.jobs.active == 3
    assert response.jobs.resumable_polling == 1
    assert response.jobs.blocked == 2
    assert response.jobs.by_state[JobState.PENDING] == 2
    assert response.jobs.by_state[JobState.COMPLETED] == 0
    assert response.outbox.total == 4
    assert response.outbox.pending == 3
    assert response.outbox.failed == 1
    assert response.recent_failures[0].id == failed_job.id
    assert response.recent_failures[0].code == "veo_timeout"
    assert response.recent_failures[0].dead_letter is True
    assert response.recent_failures[0].retryable is True
    assert len(session.execute_statements) == 4
    assert len(session.scalar_statements) == 1


def test_resumable_polling_count_statement_selects_video_polling_jobs_only():
    statement = metrics.resumable_polling_jobs_count_statement()

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "count" in sql
    assert "jobs.mode in ('t2v', 'i2v')" in sql
    assert "jobs.state = 'polling'" in sql
    assert "jobs.vertex_operation_name is not null" in sql
    assert "jobs.blocked is false" in sql
