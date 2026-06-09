from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.models import GenerationMode, Job, JobState, utc_now
from app.services.jobs import repair
from app.services.jobs.enqueue import DispatchResult


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reenqueue_pending_jobs.py"


class FakeScalarsResult:
    def __init__(self, rows: list[Job]) -> None:
        self.rows = rows

    def all(self) -> list[Job]:
        return self.rows


class FakeRepairSession:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs
        self.statements: list[object] = []
        self.events: list[str] = []

    async def __aenter__(self) -> FakeRepairSession:
        self.events.append("session_enter")
        return self

    async def __aexit__(self, *_args: object) -> bool:
        self.events.append("session_exit")
        return False

    async def scalars(self, statement: object) -> FakeScalarsResult:
        self.statements.append(statement)
        return FakeScalarsResult(self.jobs)


def _job(*, state: JobState = JobState.PENDING, blocked: bool = False) -> Job:
    now = utc_now()
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=state,
        prompt="A small cabin at sunrise",
        blocked=blocked,
        attempts=0,
        parameters={"aspect_ratio": "1:1"},
        state_history=[],
        error=None,
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def test_repair_selects_pending_unblocked_jobs_only():
    statement = repair._pending_unblocked_jobs_statement(limit=25)

    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "jobs.state = 'pending'" in sql
    assert "jobs.blocked is false" in sql
    assert "order by jobs.created_at" in sql
    assert "limit 25" in sql


async def test_repair_reenqueues_job_ids_without_payload():
    jobs = [_job(), _job()]
    session = FakeRepairSession(jobs)
    dispatch_calls: list[tuple[object, str]] = []

    async def dispatch_job(job_id, *, reason):
        dispatch_calls.append((job_id, reason))
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode="celery",
            enqueued=True,
        )

    result = await repair.reenqueue_pending_jobs(
        limit=100,
        reason="repair_pending",
        session_factory=lambda: session,
        dispatcher=dispatch_job,
    )

    assert result.selected == 2
    assert result.dispatched == 2
    assert result.failed == 0
    assert [dispatch.job_id for dispatch in result.dispatch_results] == [
        jobs[0].id,
        jobs[1].id,
    ]
    assert [dispatch.reason for dispatch in result.dispatch_results] == [
        "repair_pending",
        "repair_pending",
    ]
    assert dispatch_calls == [
        (jobs[0].id, "repair_pending"),
        (jobs[1].id, "repair_pending"),
    ]
    sent_repr = repr(dispatch_calls)
    assert "prompt" not in sent_repr
    assert "parameters" not in sent_repr


async def test_repair_does_not_mark_jobs_failed_on_enqueue_error():
    job = _job()
    session = FakeRepairSession([job])
    original_state = job.state
    original_attempts = job.attempts
    original_history = list(job.state_history)
    original_error = job.error

    async def dispatch_job(job_id, *, reason):
        return DispatchResult(
            job_id=job_id,
            reason=reason,
            mode="celery",
            enqueued=False,
            error="broker unavailable",
        )

    result = await repair.reenqueue_pending_jobs(
        session_factory=lambda: session,
        dispatcher=dispatch_job,
    )

    assert result.selected == 1
    assert result.dispatched == 0
    assert result.failed == 1
    assert len(result.dispatch_results) == 1
    assert result.dispatch_results[0].error_code == "broker_unavailable"
    assert job.state == original_state
    assert job.attempts == original_attempts
    assert job.state_history == original_history
    assert job.error == original_error


def load_cli_module():
    spec = importlib.util.spec_from_file_location("reenqueue_pending_jobs", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_reenqueue_cli_refuses_sensitive_dotenv(monkeypatch, tmp_path):
    module = load_cli_module()
    backend_root = tmp_path / "backend"
    backend_root.mkdir()
    (tmp_path / ".env").write_text("AI_PROVIDER=mock\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "BACKEND_ROOT", backend_root)

    with pytest.raises(module.RepairCliError, match="Refusing to run"):
        module._refuse_sensitive_dotenv()


def test_reenqueue_cli_prints_counts_without_payload(monkeypatch, capsys):
    module = load_cli_module()

    async def fake_run(*, limit: int):
        assert limit == 5
        return SimpleNamespace(selected=2, dispatched=1, failed=1)

    monkeypatch.setattr(module, "_refuse_sensitive_dotenv", lambda: None)
    monkeypatch.setattr(module, "_run", fake_run)

    exit_code = module.main(["--limit", "5"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.strip() == (
        "REENQUEUE COMPLETE selected=2 dispatched=1 failed=1"
    )
    assert "prompt" not in captured.out
    assert "parameters" not in captured.out
