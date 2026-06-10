from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Protocol
from typing import TypeVar

T = TypeVar("T")

DEFAULT_RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504, 408)

AwaitableFactory = Callable[[], Awaitable[T]]
Sleep = Callable[[float], Awaitable[None]]


class RetryConfigError(ValueError):
    pass


class RetrySettings(Protocol):
    provider_retry_max_attempts: int
    provider_retry_base_delay_sec: float
    provider_retry_max_delay_sec: float


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_sec: float = 1.0
    max_delay_sec: float = 20.0


def build_retry_policy(settings: RetrySettings) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=settings.provider_retry_max_attempts,
        base_delay_sec=settings.provider_retry_base_delay_sec,
        max_delay_sec=settings.provider_retry_max_delay_sec,
    )


async def with_retry(
    awaitable_factory: AwaitableFactory[T],
    *,
    max_attempts: int = 3,
    base: float = 1.0,
    max_delay: float = 20.0,
    policy: RetryPolicy | None = None,
    retryable: Collection[int] = DEFAULT_RETRYABLE_STATUS_CODES,
    sleep: Sleep = asyncio.sleep,
) -> T:
    if policy is not None:
        max_attempts = policy.max_attempts
        base = policy.base_delay_sec
        max_delay = policy.max_delay_sec

    if max_attempts < 1:
        raise RetryConfigError("max_attempts must be at least 1")
    if base < 0:
        raise RetryConfigError("base must be greater than or equal to 0")
    if max_delay < 0:
        raise RetryConfigError("max_delay must be greater than or equal to 0")

    retryable_statuses = set(retryable)
    attempt = 1

    while True:
        try:
            return await awaitable_factory()
        except Exception as exc:
            if attempt >= max_attempts or not _is_retryable(exc, retryable_statuses):
                raise

            await sleep(_delay_for_attempt(attempt, base=base, max_delay=max_delay))
            attempt += 1


def _delay_for_attempt(attempt: int, *, base: float, max_delay: float) -> float:
    return min(max_delay, base * (2 ** (attempt - 1)))


def _is_retryable(exc: Exception, retryable_statuses: set[int]) -> bool:
    retryable_attr = getattr(exc, "retryable", None)
    if retryable_attr is True:
        return True

    status_code = _extract_status_code(exc)
    if status_code is not None:
        return status_code in retryable_statuses

    return False


def _extract_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None
