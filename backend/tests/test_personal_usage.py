"""Unit contract for the G9A deep read model; PostgreSQL proof is separate."""
import asyncio
import importlib
import inspect
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from uuid import UUID

import pytest


NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
UID = UUID(int=1)
EXPECTED_METERS = (
    ("gemini_input_token", "token"),
    ("gemini_output_token", "token"),
    ("imagen_fast_image", "image"),
    ("imagen_standard_image", "image"),
    ("imagen_ultra_image", "image"),
    ("veo_fast_ms", "millisecond"),
    ("veo_standard_ms", "millisecond"),
)


def load():
    return importlib.import_module("app.personal_usage")


def test_personal_usage_exposes_one_keyword_only_interface_and_fixed_meters():
    module = load()
    signature = inspect.signature(module.read_personal_usage)
    assert tuple(signature.parameters) == ("session", "user_id", "now")
    assert signature.parameters["user_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["now"].kind is inspect.Parameter.KEYWORD_ONLY
    assert module.METER_UNITS == EXPECTED_METERS
    assert {item.name for item in fields(module.PersonalUsageView)} == {
        "plan", "pending_plan", "rate_card_version", "cycle", "credit",
        "concurrency", "usage",
    }


def test_personal_usage_views_are_immutable_and_keep_integer_accounting():
    module = load()
    meter = module.MeterUsageView("gemini_input_token", "token", 7, 11)
    cycle = module.CycleUsageView(0, NOW, NOW, 13, 17)
    credit = module.CreditBalanceView(19, 23)
    concurrency = module.ConcurrencyView(1, 3)
    view = module.PersonalUsageView("pro", None, "v1", cycle, credit, concurrency, (meter,))
    assert all(type(value) is int for value in (
        meter.observed_units, meter.charged_microcredits,
        cycle.index, cycle.allowance_microcredits, cycle.charged_microcredits,
        credit.available_microcredits, credit.held_microcredits,
        concurrency.active_requests, concurrency.limit,
    ))
    with pytest.raises(FrozenInstanceError):
        view.plan = "max"


@pytest.mark.parametrize("now", [NOW.replace(tzinfo=None), "not-a-time"])
def test_personal_usage_requires_an_active_transaction_and_aware_time(now):
    module = load()

    class Session:
        def in_transaction(self):
            return False

    with pytest.raises(module.PersonalUsageError) as caught:
        asyncio.run(module.read_personal_usage(Session(), user_id=UID, now=now))
    assert caught.value.code in {"usage_transaction_required", "usage_input_invalid"}


def test_personal_usage_public_errors_are_only_fixed_codes():
    module = load()
    assert module.PUBLIC_ERROR_CODES == frozenset({"usage_busy", "usage_unavailable"})
    for code in module.PUBLIC_ERROR_CODES:
        assert str(module.PersonalUsageError(code)) == code
