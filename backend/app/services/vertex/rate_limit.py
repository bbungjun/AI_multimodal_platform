from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class RateLimitError(ValueError):
    pass


class UnknownModelRateLimitError(RateLimitError):
    def __init__(self, model_id: str) -> None:
        super().__init__(f"No rate limiter is registered for model {model_id!r}.")


@dataclass(frozen=True)
class RateLimit:
    capacity: int
    window_seconds: float


class SlidingWindowLimiter:
    def __init__(
        self,
        *,
        capacity: int,
        window_seconds: float,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if capacity < 1:
            raise RateLimitError("capacity must be at least 1")
        if window_seconds <= 0:
            raise RateLimitError("window_seconds must be greater than 0")

        self.capacity = capacity
        self.window_seconds = float(window_seconds)
        self._clock = clock
        self._sleep = sleep
        self._events: deque[float] = deque()
        self._lock = asyncio.Lock()

    def current_size(self) -> int:
        self._prune(self._clock())
        return len(self._events)

    def estimate_wait(self) -> float:
        now = self._clock()
        self._prune(now)
        return self._estimate_wait(now)

    async def acquire(self) -> float:
        waited_seconds = 0.0

        while True:
            async with self._lock:
                now = self._clock()
                self._prune(now)
                wait_seconds = self._estimate_wait(now)

                if wait_seconds == 0.0:
                    self._events.append(now)
                    return waited_seconds

            await self._sleep(wait_seconds)
            waited_seconds += wait_seconds

    def _estimate_wait(self, now: float) -> float:
        if len(self._events) < self.capacity:
            return 0.0

        oldest = self._events[0]
        return max(0.0, oldest + self.window_seconds - now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()


DEFAULT_MODEL_LIMITS: dict[str, RateLimit] = {
    "imagen-4.0-fast-generate-001": RateLimit(capacity=75, window_seconds=60.0),
    "imagen-4.0-generate-001": RateLimit(capacity=75, window_seconds=60.0),
    "imagen-4.0-ultra-generate-001": RateLimit(capacity=75, window_seconds=60.0),
    "veo-3.0-fast-generate-001": RateLimit(capacity=10, window_seconds=60.0),
    "veo-3.0-generate-001": RateLimit(capacity=10, window_seconds=60.0),
    "gemini-2.5-flash": RateLimit(capacity=60, window_seconds=60.0),
}

LIMITERS: dict[str, SlidingWindowLimiter] = {
    model_id: SlidingWindowLimiter(
        capacity=limit.capacity,
        window_seconds=limit.window_seconds,
    )
    for model_id, limit in DEFAULT_MODEL_LIMITS.items()
}


def get_limiter(model_id: str) -> SlidingWindowLimiter:
    try:
        return LIMITERS[model_id]
    except KeyError as exc:
        raise UnknownModelRateLimitError(model_id) from exc


async def acquire(model_id: str) -> float:
    return await get_limiter(model_id).acquire()
