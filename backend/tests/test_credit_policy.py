"""A12-A15: callers exercise the pure credit policy Interface."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import importlib
import inspect

import pytest


def policy():
    assert importlib.util.find_spec("app.credit_policy"), "credit_policy_missing"
    return importlib.import_module("app.credit_policy")


RATES = {
    "gemini_input_token": 1000, "gemini_output_token": 4000,
    "imagen_fast_image": 50_000_000, "imagen_standard_image": 100_000_000,
    "imagen_ultra_image": 200_000_000, "veo_fast_ms": 60_000,
    "veo_standard_ms": 120_000,
}
MAX = 2**63 - 1
UTC = timezone.utc
SIGNUP = datetime(2024, 1, 31, 12, 34, 56, 123456, tzinfo=UTC)


@pytest.mark.parametrize("meter,rate", RATES.items())
def test_v1_exact_units_and_bigint_boundary(meter, rate):
    p = policy()
    assert p.MICROCREDITS_PER_CREDIT == 1_000_000
    assert p.RATE_CARD_VERSION == "v1"
    for units in (0, 1, 17, 1000, MAX // rate):
        result = p.quote_usage(version="v1", meter=meter, units=units)
        assert type(result) is int and result == units * rate
    with pytest.raises(ValueError, match="^credit_amount_overflow$"):
        p.quote_usage(version="v1", meter=meter, units=MAX // rate + 1)


@pytest.mark.parametrize("units", [True, False, 1.0, 0.0, "1", None, [], {}, -1, MAX + 1])
def test_invalid_units_are_refused_not_coerced(units):
    with pytest.raises(ValueError, match="^credit_units_invalid$"):
        policy().quote_usage(version="v1", meter="gemini_input_token", units=units)


@pytest.mark.parametrize("field,code", [("version", "credit_version_unknown"), ("meter", "credit_meter_unknown")])
@pytest.mark.parametrize("value", ["private-sentinel", "", True, None, [], {}])
def test_unknown_vocabulary_has_safe_errors(field, code, value):
    args = dict(version="v1", meter="gemini_input_token", units=1)
    args[field] = value
    with pytest.raises(ValueError, match=f"^{code}$"):
        policy().quote_usage(**args)


@pytest.mark.parametrize("name,credits,images,seconds,slots,excluded", [
    ("free", 1000, 1, 4, 1, {"imagen_standard_image", "imagen_ultra_image", "veo_standard_ms"}),
    ("pro", 10000, 4, 8, 3, {"imagen_ultra_image", "veo_standard_ms"}),
    ("max", 50000, 4, 8, 5, set()),
])
def test_plan_entitlements_are_exact_immutable_and_have_no_role_bypass(name, credits, images, seconds, slots, excluded):
    p = policy()
    plan = p.plan_policy(name)
    assert plan.allowance_microcredits == credits * 1_000_000
    assert plan.max_images == images and plan.max_video_seconds == seconds
    assert plan.max_concurrent_requests == slots
    assert plan.permitted_meters == frozenset(RATES) - excluded
    with pytest.raises((FrozenInstanceError, AttributeError)):
        plan.allowance_microcredits = MAX
    assert isinstance(plan.permitted_meters, frozenset)
    assert list(inspect.signature(p.plan_policy).parameters) == ["plan"]
    assert p.plan_policy(name) == plan


@pytest.mark.parametrize("value", ["master", "admin", "FREE", "", None, True, [], {}])
def test_invalid_plan_has_no_fallback(value):
    with pytest.raises(ValueError, match="^credit_plan_unknown$"):
        policy().plan_policy(value)


def test_mixed_usage_and_subsecond_video_are_exact():
    quote = policy().quote_usage
    assert quote(version="v1", meter="gemini_input_token", units=1333) + quote(
        version="v1", meter="gemini_output_token", units=777) == 4_441_000
    assert quote(version="v1", meter="veo_fast_ms", units=4001) == 240_060_000


@pytest.mark.parametrize("index,offset", [(0, 0), (0, 1), (0, 2_592_000_000_000-1),
                                          (1, 2_592_000_000_000), (11, 11*2_592_000_000_000)])
def test_signup_and_half_open_cycles_have_exact_microsecond_boundaries(index, offset):
    result = policy().cycle_bounds(signed_up_at=SIGNUP, now=SIGNUP + timedelta(microseconds=offset))
    assert result.index == index
    assert result.starts_at == SIGNUP + timedelta(days=30*index)
    assert result.ends_at - result.starts_at == timedelta(seconds=2_592_000)
    assert result.starts_at <= SIGNUP + timedelta(microseconds=offset) < result.ends_at
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.index = 1


def test_leap_year_not_calendar_month_and_offset_normalization():
    p = policy()
    result = p.cycle_bounds(signed_up_at=SIGNUP, now=SIGNUP)
    assert result.ends_at.day == 1 and result.ends_at.month == 3
    # Fixed offsets spanning DST represent aware instants without host tzdata dependency.
    signup = datetime(2024, 3, 1, 8, tzinfo=timezone(timedelta(hours=-5)))
    now = datetime(2024, 3, 31, 9, tzinfo=timezone(timedelta(hours=-4)))
    local = p.cycle_bounds(signed_up_at=signup, now=now)
    universal = p.cycle_bounds(signed_up_at=signup.astimezone(UTC), now=now.astimezone(UTC))
    assert local == universal and local.index == 1
    assert local.starts_at.tzinfo is UTC


@pytest.mark.parametrize("signup,now,code", [
    (SIGNUP, SIGNUP-timedelta(microseconds=1), "credit_time_before_signup"),
    (SIGNUP.replace(tzinfo=None), SIGNUP, "credit_time_invalid"),
    (SIGNUP, SIGNUP.replace(tzinfo=None), "credit_time_invalid"),
    (None, SIGNUP, "credit_time_invalid"),
    (SIGNUP, "private-sentinel", "credit_time_invalid"),
    (datetime.max.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC), "credit_time_overflow"),
    (datetime.min.replace(tzinfo=timezone(timedelta(hours=1))), SIGNUP, "credit_time_overflow"),
])
def test_invalid_time_fails_closed(signup, now, code):
    with pytest.raises(ValueError, match=f"^{code}$"):
        policy().cycle_bounds(signed_up_at=signup, now=now)


def test_policy_has_no_io_or_mutable_catalog():
    p = policy()
    assert set(p._PLANS) == {"free", "pro", "max"}
    with pytest.raises(TypeError):
        p._PLANS["free"] = p.plan_policy("max")
    with pytest.raises(TypeError):
        p._RATES["gemini_input_token"] = 0
    source = inspect.getsource(p)
    for forbidden in ("import os", "import sqlalchemy", "import app.db", "import http", "import google", "datetime.now(", "open("):
        assert forbidden not in source
