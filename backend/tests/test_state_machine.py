from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models import GenerationMode, Job, JobState
from app.state_machine import (
    InvalidTransitionError,
    NON_TERMINAL_STATES,
    TERMINAL_STATES,
    can_transition,
    normalize_state,
    transition,
)


def _job(*, state: JobState = JobState.PENDING) -> Job:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    return Job(
        id=uuid4(),
        mode=GenerationMode.T2I,
        model="imagen-4.0-fast-generate-001",
        state=state,
        prompt="a quiet desk lamp",
        blocked=False,
        attempts=0,
        parameters={},
        state_history=[],
        vertex_charged=False,
        created_at=now,
        updated_at=now,
    )


def test_transition_updates_state_timestamp_and_history_detail():
    job = _job()
    changed_at = datetime(2026, 5, 26, 12, 5, tzinfo=timezone.utc)

    result = transition(
        job,
        JobState.QUEUED,
        detail={"runner": "in-process"},
        at=changed_at,
    )

    assert result is job
    assert job.state == JobState.QUEUED
    assert job.updated_at == changed_at
    assert job.state_history == [
        {
            "state": "queued",
            "at": changed_at.isoformat(),
            "detail": {"runner": "in-process"},
        }
    ]


def test_transition_preserves_existing_history_entries():
    job = _job(state=JobState.QUEUED)
    job.state_history = [{"state": "queued", "at": "already"}]

    transition(job, JobState.GENERATING, detail={"rate_limit_wait_sec": 0.0})

    assert [entry["state"] for entry in job.state_history] == [
        "queued",
        "generating",
    ]
    assert job.state_history[0] == {"state": "queued", "at": "already"}
    assert job.state_history[1]["detail"] == {"rate_limit_wait_sec": 0.0}


def test_invalid_transition_is_rejected_without_mutating_job():
    job = _job(state=JobState.COMPLETED)
    job.state_history = [{"state": "completed", "at": "already"}]
    updated_at = job.updated_at

    with pytest.raises(InvalidTransitionError) as exc_info:
        transition(job, JobState.QUEUED)

    assert str(exc_info.value) == "Invalid job state transition: completed -> queued"
    assert job.state == JobState.COMPLETED
    assert job.updated_at == updated_at
    assert job.state_history == [{"state": "completed", "at": "already"}]


def test_state_helpers_normalize_strings_and_report_allowed_transitions():
    assert normalize_state("pending") == JobState.PENDING
    assert can_transition("pending", "queued") is True
    assert can_transition(JobState.PENDING, JobState.DOWNLOADING) is False

    with pytest.raises(InvalidTransitionError) as exc_info:
        normalize_state("not-a-state")

    assert str(exc_info.value) == "Unknown job state: not-a-state"


def test_terminal_and_non_terminal_state_sets_are_partitioned():
    assert TERMINAL_STATES == {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
    }
    assert JobState.PENDING in NON_TERMINAL_STATES
    assert JobState.POLLING in NON_TERMINAL_STATES
    assert TERMINAL_STATES.isdisjoint(NON_TERMINAL_STATES)
    assert TERMINAL_STATES | NON_TERMINAL_STATES == set(JobState)
