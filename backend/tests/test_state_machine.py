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


EXPECTED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {
        JobState.ENHANCING,
        JobState.QUEUED,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.ENHANCING: {
        JobState.QUEUED,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.QUEUED: {
        JobState.GENERATING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.GENERATING: {
        JobState.POLLING,
        JobState.DOWNLOADING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.POLLING: {
        JobState.POLLING,
        JobState.DOWNLOADING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.DOWNLOADING: {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


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


def test_transition_records_null_detail_when_no_detail_is_supplied():
    job = _job(state=JobState.DOWNLOADING)
    changed_at = datetime(2026, 5, 26, 12, 8, tzinfo=timezone.utc)

    transition(job, JobState.COMPLETED, at=changed_at)

    assert job.state_history == [
        {
            "state": "completed",
            "at": changed_at.isoformat(),
            "detail": None,
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


def test_state_machine_allows_only_the_documented_transition_matrix():
    assert set(EXPECTED_TRANSITIONS) == set(JobState)

    for current_state in JobState:
        for target_state in JobState:
            assert can_transition(current_state, target_state) is (
                target_state in EXPECTED_TRANSITIONS[current_state]
            ), f"{current_state.value} -> {target_state.value}"


@pytest.mark.parametrize("terminal_state", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_terminal_states_reject_every_outgoing_transition_without_mutation(
    terminal_state: JobState,
):
    job = _job(state=terminal_state)
    job.state_history = [{"state": terminal_state.value, "at": "already"}]
    updated_at = job.updated_at

    for target_state in JobState:
        with pytest.raises(InvalidTransitionError):
            transition(job, target_state)

        assert job.state == terminal_state
        assert job.updated_at == updated_at
        assert job.state_history == [{"state": terminal_state.value, "at": "already"}]


def test_polling_can_record_a_polling_heartbeat_transition():
    job = _job(state=JobState.POLLING)
    changed_at = datetime(2026, 5, 26, 12, 10, tzinfo=timezone.utc)

    transition(
        job,
        JobState.POLLING,
        detail={"operation_name": "operations/demo"},
        at=changed_at,
    )

    assert job.state == JobState.POLLING
    assert job.state_history == [
        {
            "state": "polling",
            "at": changed_at.isoformat(),
            "detail": {"operation_name": "operations/demo"},
        }
    ]
