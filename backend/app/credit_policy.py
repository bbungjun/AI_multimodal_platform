"""Pure, versioned credit policy. No account mutation or provider price parity."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType

MICROCREDITS_PER_CREDIT = 1_000_000
RATE_CARD_VERSION = "v1"
_MAX_BIGINT = 2**63 - 1
_CYCLE = timedelta(seconds=2_592_000)
_RATES = MappingProxyType({
    "gemini_input_token": 1000,
    "gemini_output_token": 4000,
    "imagen_fast_image": 50_000_000,
    "imagen_standard_image": 100_000_000,
    "imagen_ultra_image": 200_000_000,
    "veo_fast_ms": 60_000,
    "veo_standard_ms": 120_000,
})


@dataclass(frozen=True)
class PlanPolicy:
    allowance_microcredits: int
    permitted_meters: frozenset[str]
    max_images: int
    max_video_seconds: int
    max_concurrent_requests: int


_PLANS = MappingProxyType({
    "free": PlanPolicy(1000 * MICROCREDITS_PER_CREDIT, frozenset(_RATES) - {
        "imagen_standard_image", "imagen_ultra_image", "veo_standard_ms"}, 1, 4, 1),
    "pro": PlanPolicy(10000 * MICROCREDITS_PER_CREDIT, frozenset(_RATES) - {
        "imagen_ultra_image", "veo_standard_ms"}, 4, 8, 3),
    "max": PlanPolicy(50000 * MICROCREDITS_PER_CREDIT, frozenset(_RATES), 4, 8, 5),
})


def plan_policy(plan: str) -> PlanPolicy:
    if type(plan) is not str or plan not in _PLANS:
        raise ValueError("credit_plan_unknown")
    return _PLANS[plan]


def quote_usage(*, version: str, meter: str, units: int) -> int:
    if type(version) is not str or version != RATE_CARD_VERSION:
        raise ValueError("credit_version_unknown")
    if type(meter) is not str or meter not in _RATES:
        raise ValueError("credit_meter_unknown")
    if type(units) is not int or not 0 <= units <= _MAX_BIGINT:
        raise ValueError("credit_units_invalid")
    result = units * _RATES[meter]
    if result > _MAX_BIGINT:
        raise ValueError("credit_amount_overflow")
    return result


@dataclass(frozen=True)
class CycleBounds:
    index: int
    starts_at: datetime
    ends_at: datetime


def cycle_bounds(*, signed_up_at: datetime, now: datetime) -> CycleBounds:
    try:
        if any(not isinstance(value, datetime) or value.utcoffset() is None
               for value in (signed_up_at, now)):
            raise ValueError("credit_time_invalid")
        signup_utc = signed_up_at.astimezone(timezone.utc)
        now_utc = now.astimezone(timezone.utc)
        if now_utc < signup_utc:
            raise ValueError("credit_time_before_signup")
        # timedelta floor division preserves microseconds; total_seconds() floats do not.
        index = (now_utc - signup_utc) // _CYCLE
        start = signup_utc + index * _CYCLE
        return CycleBounds(index, start, start + _CYCLE)
    except OverflowError:
        raise ValueError("credit_time_overflow") from None
