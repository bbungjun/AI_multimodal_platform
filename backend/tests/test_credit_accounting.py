"""Tests cross only the public accounting Interface; PostgreSQL proof is separate."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

import app.credit_accounting as accounting
from app.credit_lifecycle import grant_bonus
from app.credit_models import (
    CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent, CreditOperation,
    CreditReservation, CreditReservationAllocation, CreditReservationItem,
    CreditUsageRecord,
)
from app.identity_models import User

NOW = datetime(2024, 2, 29, 10, 30, 0, 123456, tzinfo=timezone.utc)
UID = UUID(int=1)
RID = UUID(int=2)


class EmptySession:
    def __init__(self, active=True):
        self.active = active

    def in_transaction(self):
        return self.active

    @asynccontextmanager
    async def begin_nested(self):
        yield


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class MemorySession(EmptySession):
    """Statement-contract fake; real lock/FK behavior belongs to the fixed proof."""
    def __init__(self, *, role="user", status="active", active=True):
        super().__init__(active)
        self.rows = {User: [User(id=UID, role=role, status=status, signed_up_at=NOW)]}
        self.statements = []

    @asynccontextmanager
    async def begin_nested(self):
        before = deepcopy(self.rows)
        try:
            yield
        except BaseException:
            self.rows = before
            raise

    def add(self, row):
        self.rows.setdefault(type(row), []).append(row)

    async def flush(self):
        return None

    def select(self, statement):
        self.statements.append(statement)
        model = statement.column_descriptions[0]["entity"]
        rows = list(self.rows.get(model, []))
        for criterion in statement._where_criteria:
            rows = [row for row in rows if getattr(row, criterion.left.key) == criterion.right.value]
        if model is CreditCycle:
            rows.sort(key=lambda row: row.cycle_index, reverse=True)
        elif model is CreditGrant:
            rows.sort(key=lambda row: row.id)
        elif model is CreditReservationItem:
            rows.sort(key=lambda row: row.meter)
        elif model is CreditLedgerEvent:
            rows.sort(key=lambda row: (row.created_at, row.id))
        return rows

    async def scalar(self, statement):
        rows = self.select(statement)
        return rows[0] if rows else None

    async def scalars(self, statement):
        return Rows(self.select(statement))


def run(call):
    return asyncio.run(call)


def request(*estimates, key="reserve_1", user_id=UID):
    return accounting.ReservationRequest(user_id, key, tuple(estimates))


def estimate(meter="gemini_input_token", units=1):
    return accounting.UsageEstimate(meter, units)


def report(*lines):
    return accounting.UsageReport(tuple(lines))


def line(meter="gemini_input_token", units=1, source="mock_estimate"):
    return accounting.UsageLine(meter, units, source)


def reserve(s, *estimates, key="reserve_1", now=NOW):
    return run(accounting.reserve(s, request=request(*estimates, key=key), now=now))


def snapshot(s):
    classes = (CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent, CreditOperation,
               CreditReservation, CreditReservationItem, CreditReservationAllocation,
               CreditUsageRecord)
    return {cls: [tuple(getattr(row, col.name) for col in cls.__table__.columns)
                  for row in s.rows.get(cls, [])] for cls in classes}


def test_public_interface_and_values_are_immutable():
    assert set(accounting.__all__) == {
        "reserve", "settle", "release", "CreditAccountingError",
        "UsageEstimate", "ReservationRequest", "UsageLine", "UsageReport",
        "ReservationReceipt", "TerminalReceipt",
    }
    value = estimate()
    with pytest.raises(FrozenInstanceError):
        value.maximum_units = 2


@pytest.mark.parametrize("bad", [None, "id", 1])
def test_reserve_rejects_non_request_without_touching_session(bad):
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.reserve(EmptySession(), request=bad, now=NOW))


@pytest.mark.parametrize("bad", [[], (), (estimate(units=0),), (estimate(units=True),),
                                 (estimate(meter="unknown"),),
                                 (estimate(), estimate())])
def test_reserve_input_is_strict_and_unique(bad):
    value = request(*bad) if isinstance(bad, list) else accounting.ReservationRequest(UID, "reserve_1", bad)
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.reserve(EmptySession(), request=value, now=NOW))


@pytest.mark.parametrize("key", ["", "space key", "x" * 97, 7])
def test_safe_operation_key(key):
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.reserve(EmptySession(), request=request(estimate(), key=key), now=NOW))


@pytest.mark.parametrize("now", [NOW.replace(tzinfo=None), "time", None])
def test_aware_time_required(now):
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.reserve(EmptySession(), request=request(estimate()), now=now))


def test_active_outer_transaction_required():
    with pytest.raises(accounting.CreditAccountingError, match="^credit_transaction_required$"):
        run(accounting.reserve(EmptySession(False), request=request(estimate()), now=NOW))


@pytest.mark.parametrize("delivery", ["", "no_deliverable", 1])
def test_settle_delivery_is_closed(delivery):
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.settle(EmptySession(), user_id=UID, reservation_id=RID,
                              usage=report(line()), delivery=delivery,
                              operation_key="terminal_1", now=NOW))


@pytest.mark.parametrize("reason", ["", "free text", "other", 1])
def test_release_reason_is_closed(reason):
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.release(EmptySession(), user_id=UID, reservation_id=RID,
                               usage=report(), reason_code=reason,
                               operation_key="terminal_1", now=NOW))


@pytest.mark.parametrize("usage", [report(), report(line(units=-1)), report(line(source="raw")),
                                   report(line(), line())])
def test_settle_usage_is_nonempty_strict_and_unique(usage):
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        run(accounting.settle(EmptySession(), user_id=UID, reservation_id=RID,
                              usage=usage, delivery="delivered",
                              operation_key="terminal_1", now=NOW))


def test_reserve_creates_hold_items_allocation_and_ledger():
    s = MemorySession()
    receipt = reserve(s, estimate("gemini_output_token", 2), estimate("gemini_input_token", 3))
    assert receipt.status == "held" and receipt.reserved_microcredits == 11_000
    assert not receipt.replayed and receipt.rate_card_version == "v1"
    assert [(row.meter, row.maximum_units, row.quoted_microcredits)
            for row in s.rows[CreditReservationItem]] == [
                ("gemini_input_token", 3, 3_000),
                ("gemini_output_token", 2, 8_000),
            ]
    assert [row.reserved_microcredits for row in s.rows[CreditReservationAllocation]] == [11_000]
    grant = s.rows[CreditGrant][0]
    assert grant.reserved_microcredits == 11_000
    reserve_events = [row for row in s.rows[CreditLedgerEvent] if row.kind == "reserve"]
    assert len(reserve_events) == 1 and reserve_events[0].reserved_delta == 11_000


def test_reserve_replay_precedes_renewal_and_suspension():
    s = MemorySession()
    first = reserve(s, estimate())
    before = snapshot(s)
    s.rows[User][0].status = "suspended"
    replayed = reserve(s, estimate(), now=NOW + timedelta(days=90))
    assert replayed.replayed and replayed.reservation_id == first.reservation_id
    assert snapshot(s) == before


def test_reserve_collision_and_exhaustion_are_atomic():
    s = MemorySession()
    reserve(s, estimate())
    before = snapshot(s)
    with pytest.raises(accounting.CreditAccountingError, match="^credit_idempotency_conflict$"):
        reserve(s, estimate(units=2))
    assert snapshot(s) == before

    empty = MemorySession()
    with pytest.raises(accounting.CreditAccountingError, match="^monthly_credit_exhausted$"):
        reserve(empty, estimate(units=1_000_001))
    assert set(empty.rows) == {User}


def test_reserve_uses_expiring_first_allocation_not_lock_order():
    s = MemorySession(role="master")
    async def scenario():
        await grant_bonus(s, user_id=UID, amount_microcredits=5_000,
                          expires_at=NOW + timedelta(days=1), reason_code="promo",
                          operation_key="bonus_1", now=NOW)
        return await accounting.reserve(
            s, request=request(estimate(units=6), key="reserve_multi"), now=NOW)
    receipt = run(scenario())
    allocations = sorted(s.rows[CreditReservationAllocation], key=lambda row: row.ordinal)
    bonus = next(row for row in s.rows[CreditGrant] if row.kind == "bonus")
    assert receipt.reserved_microcredits == 6_000
    assert allocations[0].grant_id == bonus.id and allocations[0].reserved_microcredits == 5_000
    assert allocations[1].reserved_microcredits == 1_000


def test_free_plan_refuses_unentitled_meter_and_suspended_new_hold():
    s = MemorySession()
    with pytest.raises(accounting.CreditAccountingError, match="^credit_plan_refused$"):
        reserve(s, estimate("imagen_ultra_image", 1))
    assert set(s.rows) == {User}
    suspended = MemorySession(status="suspended")
    with pytest.raises(accounting.CreditAccountingError, match="^credit_plan_refused$"):
        reserve(suspended, estimate())
    assert set(suspended.rows) == {User}
