from __future__ import annotations

import pytest

from app.services import rate_limit


class ManualClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_sliding_window_limiter_rejects_invalid_config():
    with pytest.raises(rate_limit.RateLimitError, match="capacity"):
        rate_limit.SlidingWindowLimiter(capacity=0, window_seconds=60.0)

    with pytest.raises(rate_limit.RateLimitError, match="window_seconds"):
        rate_limit.SlidingWindowLimiter(capacity=1, window_seconds=0.0)


async def test_sliding_window_limiter_allows_capacity_without_sleeping():
    clock = ManualClock()
    limiter = rate_limit.SlidingWindowLimiter(
        capacity=2,
        window_seconds=10.0,
        clock=clock,
        sleep=clock.sleep,
    )

    first_wait = await limiter.acquire()
    second_wait = await limiter.acquire()

    assert first_wait == 0.0
    assert second_wait == 0.0
    assert clock.sleeps == []
    assert limiter.current_size() == 2
    assert limiter.estimate_wait() == 10.0


async def test_sliding_window_limiter_waits_until_oldest_event_expires():
    clock = ManualClock()
    limiter = rate_limit.SlidingWindowLimiter(
        capacity=1,
        window_seconds=3.0,
        clock=clock,
        sleep=clock.sleep,
    )

    assert await limiter.acquire() == 0.0
    assert limiter.estimate_wait() == 3.0

    second_wait = await limiter.acquire()

    assert second_wait == 3.0
    assert clock.now == 3.0
    assert clock.sleeps == [3.0]
    assert limiter.current_size() == 1


async def test_acquire_uses_registered_model_limiter(monkeypatch):
    class FakeLimiter:
        def __init__(self) -> None:
            self.calls = 0

        async def acquire(self) -> float:
            self.calls += 1
            return 1.25

    limiter = FakeLimiter()
    monkeypatch.setitem(rate_limit.LIMITERS, "demo-model", limiter)

    assert await rate_limit.acquire("demo-model") == 1.25
    assert limiter.calls == 1


def test_default_model_limit_registry_matches_submission_contract():
    assert rate_limit.DEFAULT_MODEL_LIMITS["imagen-4.0-fast-generate-001"] == (
        rate_limit.RateLimit(capacity=5, window_seconds=60.0)
    )
    assert rate_limit.DEFAULT_MODEL_LIMITS["veo-3.0-fast-generate-001"] == (
        rate_limit.RateLimit(capacity=1, window_seconds=60.0)
    )
    assert rate_limit.DEFAULT_MODEL_LIMITS["gemini-2.5-flash"] == (
        rate_limit.RateLimit(capacity=10, window_seconds=60.0)
    )
    assert rate_limit.get_limiter("imagen-4.0-generate-001").capacity == 5
    assert rate_limit.get_limiter("veo-3.0-generate-001").capacity == 1


def test_build_model_limits_uses_settings_override():
    settings = rate_limit.RateLimitSettings(
        rate_limit_imagen_per_min=3,
        rate_limit_veo_per_min=2,
        rate_limit_gemini_per_min=7,
    )

    limits = rate_limit.build_model_limits(settings)

    assert limits["imagen-4.0-fast-generate-001"] == rate_limit.RateLimit(
        capacity=3,
        window_seconds=60.0,
    )
    assert limits["imagen-4.0-generate-001"].capacity == 3
    assert limits["veo-3.0-fast-generate-001"] == rate_limit.RateLimit(
        capacity=2,
        window_seconds=60.0,
    )
    assert limits["veo-3.0-generate-001"].capacity == 2
    assert limits["gemini-2.5-flash"] == rate_limit.RateLimit(
        capacity=7,
        window_seconds=60.0,
    )


def test_build_default_model_limits_uses_runtime_settings(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("RATE_LIMIT_IMAGEN_PER_MIN", "4")
    monkeypatch.setenv("RATE_LIMIT_VEO_PER_MIN", "2")
    monkeypatch.setenv("RATE_LIMIT_GEMINI_PER_MIN", "8")
    get_settings.cache_clear()

    try:
        limits = rate_limit.build_default_model_limits()
    finally:
        get_settings.cache_clear()

    assert limits["imagen-4.0-generate-001"].capacity == 4
    assert limits["veo-3.0-generate-001"].capacity == 2
    assert limits["gemini-2.5-flash"].capacity == 8


def test_get_limiter_rejects_unknown_model_id():
    with pytest.raises(rate_limit.UnknownModelRateLimitError, match="unknown-model"):
        rate_limit.get_limiter("unknown-model")
