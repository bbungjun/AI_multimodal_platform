from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import Job, JobState


STATES: tuple[JobState, ...] = tuple(JobState)
TERMINAL_STATES: frozenset[JobState] = frozenset(
    {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
)
NON_TERMINAL_STATES: frozenset[JobState] = frozenset(
    state for state in STATES if state not in TERMINAL_STATES
)

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PENDING: frozenset(
        {JobState.ENHANCING, JobState.QUEUED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.ENHANCING: frozenset(
        {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.QUEUED: frozenset(
        {JobState.GENERATING, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.GENERATING: frozenset(
        {
            JobState.POLLING,
            JobState.DOWNLOADING,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.POLLING: frozenset(
        {
            JobState.POLLING,
            JobState.DOWNLOADING,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.DOWNLOADING: frozenset(
        {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


class InvalidTransitionError(ValueError):
    pass


def normalize_state(state: JobState | str) -> JobState:
    try:
        return state if isinstance(state, JobState) else JobState(state)
    except ValueError as exc:
        raise InvalidTransitionError(f"Unknown job state: {state}") from exc


def can_transition(current_state: JobState | str, new_state: JobState | str) -> bool:
    current = normalize_state(current_state)
    target = normalize_state(new_state)
    return target in ALLOWED_TRANSITIONS[current]


def transition(
    job: Job,
    new_state: JobState | str,
    *,
    detail: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> Job:
    current = normalize_state(job.state)
    target = normalize_state(new_state)

    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"Invalid job state transition: {current.value} -> {target.value}"
        )

    changed_at = at or datetime.now(timezone.utc)
    job.state = target
    job.updated_at = changed_at

    history = list(job.state_history or [])
    entry: dict[str, Any] = {
        "state": target.value,
        "at": changed_at.isoformat(),
    }
    if detail is not None:
        entry["detail"] = detail
    history.append(entry)
    job.state_history = history

    return job
