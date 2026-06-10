from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services import retry


class ProviderError(Exception):
    def __init__(self, message: str = "provider error", **attrs: object) -> None:
        super().__init__(message)
        for name, value in attrs.items():
            setattr(self, name, value)


class RecorderSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def test_default_retryable_status_codes_match_submission_contract():
    assert retry.DEFAULT_RETRYABLE_STATUS_CODES == (429, 500, 502, 503, 504, 408)


def test_build_retry_policy_uses_settings_override():
    settings = Settings(
        _env_file=None,
        provider_retry_max_attempts=2,
        provider_retry_base_delay_sec=0.25,
        provider_retry_max_delay_sec=2.5,
    )

    assert retry.build_retry_policy(settings) == retry.RetryPolicy(
        max_attempts=2,
        base_delay_sec=0.25,
        max_delay_sec=2.5,
    )


async def test_with_retry_retries_status_code_errors_then_returns_result():
    attempts = 0
    sleep = RecorderSleep()

    async def call_provider() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ProviderError(status_code=429)
        return "ok"

    result = await retry.with_retry(
        call_provider,
        base=0.5,
        max_delay=5.0,
        sleep=sleep,
    )

    assert result == "ok"
    assert attempts == 3
    assert sleep.delays == [0.5, 1.0]


async def test_with_retry_fails_non_retryable_4xx_without_sleeping():
    attempts = 0
    sleep = RecorderSleep()

    async def call_provider() -> str:
        nonlocal attempts
        attempts += 1
        raise ProviderError("bad request", status_code=400)

    with pytest.raises(ProviderError, match="bad request"):
        await retry.with_retry(call_provider, sleep=sleep)

    assert attempts == 1
    assert sleep.delays == []


async def test_with_retry_stops_at_max_attempts_and_raises_last_error():
    attempts = 0
    sleep = RecorderSleep()

    async def call_provider() -> str:
        nonlocal attempts
        attempts += 1
        raise ProviderError(f"temporary failure {attempts}", status_code=503)

    with pytest.raises(ProviderError, match="temporary failure 3"):
        await retry.with_retry(
            call_provider,
            max_attempts=3,
            base=0.25,
            sleep=sleep,
        )

    assert attempts == 3
    assert sleep.delays == [0.25, 0.5]


async def test_with_retry_caps_exponential_backoff_delay():
    attempts = 0
    sleep = RecorderSleep()

    async def call_provider() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise ProviderError(status_code=503)
        return "ok"

    result = await retry.with_retry(
        call_provider,
        max_attempts=4,
        base=1.0,
        max_delay=1.5,
        sleep=sleep,
    )

    assert result == "ok"
    assert attempts == 4
    assert sleep.delays == [1.0, 1.5, 1.5]


@pytest.mark.parametrize(
    "exc",
    [
        ProviderError(status_code=408),
        ProviderError(code=500),
        ProviderError(status=502),
        ProviderError(response=SimpleNamespace(status_code=504)),
        ProviderError(retryable=True),
    ],
)
async def test_with_retry_detects_retryable_errors_from_common_exception_shapes(exc):
    attempts = 0
    sleep = RecorderSleep()

    async def call_provider() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise exc
        return "ok"

    assert await retry.with_retry(call_provider, sleep=sleep) == "ok"
    assert attempts == 2
    assert sleep.delays == [1.0]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_attempts": 0}, "max_attempts"),
        ({"base": -0.1}, "base"),
        ({"max_delay": -0.1}, "max_delay"),
    ],
)
async def test_with_retry_rejects_invalid_config(kwargs, message):
    async def call_provider() -> str:
        return "unused"

    with pytest.raises(retry.RetryConfigError, match=message):
        await retry.with_retry(call_provider, **kwargs)
