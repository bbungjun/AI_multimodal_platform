"""Unit contract for the G9A deep read model; PostgreSQL proof is separate."""
import asyncio
import importlib
import inspect
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.credit_lifecycle import CycleView
from app.credit_models import CreditGrant, CreditReservation, CreditUsageRecord


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


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class UsageSession:
    def __init__(self, rows=None, *, active=True):
        self.rows = rows or {}
        self.active = active
        self.statements = []

    def in_transaction(self):
        return self.active

    class Savepoint:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_):
            return False

    def begin_nested(self):
        return self.Savepoint()

    async def scalars(self, statement):
        self.statements.append(statement)
        model = statement.column_descriptions[0]["entity"]
        rows = list(self.rows.get(model, []))
        for criterion in statement._where_criteria:
            key = criterion.left.key
            value = criterion.right.value
            operator = criterion.operator.__name__
            if operator == "eq":
                rows = [row for row in rows if getattr(row, key) == value]
            elif operator == "ge":
                rows = [row for row in rows if getattr(row, key) >= value]
            elif operator == "le":
                rows = [row for row in rows if getattr(row, key) <= value]
        return Rows(rows)


def cycle(*, plan="free", pending=None, index=0):
    from datetime import timedelta

    return CycleView(
        UID, plan, pending, UUID(int=2), index, NOW, NOW + timedelta(days=30),
        {"free": 1_000_000_000, "pro": 10_000_000_000, "max": 50_000_000_000}[plan],
        UUID(int=3),
    )


def grant(*, amount=1_000_000_000, reserved=0, consumed=0, expired=0, identifier=3):
    return CreditGrant(
        id=UUID(int=identifier), user_id=UID, cycle_id=UUID(int=2), kind="base",
        created_at=NOW, expires_at=NOW, reason_code="cycle_base",
        granted_microcredits=amount, reserved_microcredits=reserved,
        consumed_microcredits=consumed, expired_microcredits=expired,
    )


def reservation(*, amount=20, identifier=4):
    return CreditReservation(
        id=UUID(int=identifier), user_id=UID, reserve_operation_key="reserve",
        rate_card_version="v1", status="held", reserved_microcredits=amount,
        created_at=NOW, terminal_operation_key=None, terminal_at=None,
        terminal_reason_code=None, delivery=None,
    )


def usage(meter, units, charged, *, delivery="delivered", identifier=4):
    return CreditUsageRecord(
        reservation_id=UUID(int=identifier), user_id=UID, meter=meter,
        terminal_operation_key=f"terminal_{identifier}_{meter}", rate_card_version="v1",
        actual_units=units, charged_microcredits=charged, recorded_at=NOW,
        source="mock_estimate", delivery=delivery,
    )


def read(monkeypatch, session, view=None):
    module = load()

    async def ensured(received, *, user_id, now):
        assert received is session and user_id == UID and now == NOW
        return view or cycle()

    monkeypatch.setattr(module, "ensure_cycle", ensured)
    return asyncio.run(module.read_personal_usage(session, user_id=UID, now=NOW))


@pytest.mark.parametrize("plan,limit", [("free", 1), ("pro", 3), ("max", 5)])
def test_personal_usage_zero_shape_plan_limit_and_pending(monkeypatch, plan, limit):
    base = grant(amount={"free": 1_000_000_000, "pro": 10_000_000_000, "max": 50_000_000_000}[plan])
    result = read(monkeypatch, UsageSession({CreditGrant: [base]}), cycle(plan=plan, pending="free" if plan != "free" else None))
    assert result.plan == plan and result.pending_plan == ("free" if plan != "free" else None)
    assert result.concurrency.limit == limit and result.concurrency.active_requests == 0
    assert tuple((row.meter, row.unit, row.observed_units, row.charged_microcredits) for row in result.usage) == tuple(
        (meter, unit, 0, 0) for meter, unit in EXPECTED_METERS
    )


def test_personal_usage_aggregates_bonus_hold_and_no_deliverable(monkeypatch):
    rows = {
        CreditGrant: [
            grant(reserved=20, consumed=30),
            grant(amount=100, consumed=10, identifier=9),
        ],
        CreditReservation: [reservation(amount=20)],
        CreditUsageRecord: [
            usage("gemini_input_token", 1000, 1_000_000),
            usage("gemini_input_token", 12, 0, delivery="no_deliverable", identifier=5),
            usage("imagen_fast_image", 2, 100_000_000, identifier=6),
        ],
    }
    result = read(monkeypatch, UsageSession(rows))
    assert result.credit.available_microcredits == 1_000_000_040
    assert result.credit.held_microcredits == 20
    assert result.concurrency.active_requests == 1
    assert result.cycle.charged_microcredits == 101_000_000
    assert result.usage[0].observed_units == 1012
    assert result.usage[0].charged_microcredits == 1_000_000


@pytest.mark.parametrize("corruption", ["drift", "unknown_meter", "overflow", "too_many"])
def test_personal_usage_corruption_fails_closed(monkeypatch, corruption):
    rows = {CreditGrant: [grant()]}
    view = cycle()
    if corruption == "drift":
        rows[CreditReservation] = [reservation()]
    elif corruption == "unknown_meter":
        rows[CreditUsageRecord] = [usage("unknown", 1, 0)]
    elif corruption == "overflow":
        rows[CreditGrant] = [grant(amount=2**63 - 1), grant(amount=1, identifier=10)]
    else:
        view = cycle(plan="free")
        rows[CreditGrant] = [grant(reserved=2)]
        rows[CreditReservation] = [reservation(amount=1), reservation(amount=1, identifier=5)]
    with pytest.raises(load().PersonalUsageError, match="^usage_unavailable$"):
        read(monkeypatch, UsageSession(rows), view)
