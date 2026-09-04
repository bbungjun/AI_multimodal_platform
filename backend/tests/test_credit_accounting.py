"""Tests cross only the public accounting Interface; PostgreSQL proof is separate."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

import app.credit_accounting as accounting
from app.credit_lifecycle import ensure_cycle, grant_bonus
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
        elif model is CreditReservationAllocation:
            rows.sort(key=lambda row: row.ordinal)
        elif model is CreditUsageRecord:
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


def settle(s, rid, *lines, key="terminal_1", delivery="delivered", now=NOW):
    return run(accounting.settle(
        s, user_id=UID, reservation_id=rid, usage=report(*lines), delivery=delivery,
        operation_key=key, now=now))


def release(s, rid, *lines, key="terminal_1", reason="provider_failed", now=NOW):
    return run(accounting.release(
        s, user_id=UID, reservation_id=rid, usage=report(*lines), reason_code=reason,
        operation_key=key, now=now))


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
    assert reserve(s, estimate(), now=NOW - timedelta(microseconds=1)).replayed


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


def test_free_concurrency_limit_is_atomic_and_replay_precedes_capacity():
    s = MemorySession()
    first = reserve(s, estimate(), key="slot_1")
    before = snapshot(s)

    replayed = reserve(s, estimate(), key="slot_1")
    assert replayed.replayed and replayed.reservation_id == first.reservation_id
    assert snapshot(s) == before

    with pytest.raises(accounting.CreditAccountingError, match="^user_concurrency_limit$"):
        reserve(s, estimate(), key="slot_2")
    assert snapshot(s) == before


def test_plan_permission_precedes_concurrency_and_terminal_returns_slot():
    s = MemorySession()
    first = reserve(s, estimate(), key="slot_1")
    before = snapshot(s)
    with pytest.raises(accounting.CreditAccountingError, match="^credit_plan_refused$"):
        reserve(s, estimate("imagen_ultra_image"), key="not_allowed")
    assert snapshot(s) == before

    release(s, first.reservation_id, key="return_slot")
    second = reserve(s, estimate(), key="slot_2")
    assert second.status == "held" and second.reservation_id != first.reservation_id


def test_master_uses_max_plan_five_slot_limit_without_bypass():
    s = MemorySession(role="master")
    held = [reserve(s, estimate(), key=f"master_slot_{index}") for index in range(5)]
    assert len({item.reservation_id for item in held}) == 5
    with pytest.raises(accounting.CreditAccountingError, match="^user_concurrency_limit$"):
        reserve(s, estimate(), key="master_slot_6")


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


def test_settle_preserves_usage_and_consumes_then_releases_hold():
    s = MemorySession()
    held = reserve(s, estimate("gemini_input_token", 10), estimate("gemini_output_token", 4))
    receipt = settle(s, held.reservation_id,
                     line("gemini_input_token", 4, "platform_measured"),
                     line("gemini_output_token", 1, "provider_reported"),
                     delivery="partial")
    assert receipt.status == "settled" and receipt.consumed_microcredits == 8_000
    assert receipt.released_microcredits == 18_000 and receipt.usage_line_count == 2
    assert [(row.actual_units, row.charged_microcredits, row.source, row.delivery)
            for row in s.rows[CreditUsageRecord]] == [
                (4, 4_000, "platform_measured", "partial"),
                (1, 4_000, "provider_reported", "partial"),
            ]
    grant = s.rows[CreditGrant][0]
    assert grant.reserved_microcredits == 0 and grant.consumed_microcredits == 8_000
    event = [row for row in s.rows[CreditLedgerEvent] if row.kind == "settle"][0]
    assert (event.reserved_delta, event.consumed_delta, event.expired_delta) == (-26_000, 8_000, 0)


def test_release_records_attempt_without_charge_and_allows_empty_usage():
    s = MemorySession()
    first = reserve(s, estimate(units=5), key="r1")
    result = release(s, first.reservation_id, line(units=3, source="estimated"),
                     key="t1", reason="provider_timeout")
    assert result.status == "released" and result.consumed_microcredits == 0
    assert result.released_microcredits == 5_000 and result.usage_line_count == 1
    assert s.rows[CreditUsageRecord][0].charged_microcredits == 0

    second = reserve(s, estimate(units=2), key="r2")
    empty = release(s, second.reservation_id, key="t2", reason="cancelled_before_delivery")
    assert empty.usage_line_count == 0 and empty.released_microcredits == 2_000


def test_terminal_replay_and_changed_payload_collision():
    s = MemorySession()
    held = reserve(s, estimate(units=5))
    first = settle(s, held.reservation_id, line(units=2))
    before = snapshot(s)
    replayed = settle(s, held.reservation_id, line(units=2))
    assert replayed.replayed and replayed == accounting.TerminalReceipt(
        first.reservation_id, first.operation_key, first.status,
        first.consumed_microcredits, first.released_microcredits,
        first.usage_line_count, first.effective_at, True)
    assert snapshot(s) == before
    run(ensure_cycle(s, user_id=UID, now=NOW + timedelta(days=30)))
    assert settle(s, held.reservation_id, line(units=2), now=NOW).replayed
    after_renewal = snapshot(s)
    with pytest.raises(accounting.CreditAccountingError, match="^credit_idempotency_conflict$"):
        settle(s, held.reservation_id, line(units=3))
    assert snapshot(s) == after_renewal


def test_second_terminal_key_and_cross_owner_are_safe():
    s = MemorySession()
    held = reserve(s, estimate(units=5))
    release(s, held.reservation_id)
    before = snapshot(s)
    with pytest.raises(accounting.CreditAccountingError, match="^credit_reservation_state_conflict$"):
        release(s, held.reservation_id, key="terminal_2")
    assert snapshot(s) == before
    with pytest.raises(accounting.CreditAccountingError, match="^credit_reservation_missing$"):
        release(s, UUID(int=999), key="terminal_3")


def test_usage_above_hold_and_zero_charge_settle_are_atomic():
    s = MemorySession()
    held = reserve(s, estimate(units=5))
    before = snapshot(s)
    with pytest.raises(accounting.CreditAccountingError, match="^credit_usage_exceeds_reservation$"):
        settle(s, held.reservation_id, line(units=6))
    assert snapshot(s) == before
    with pytest.raises(accounting.CreditAccountingError, match="^credit_input_invalid$"):
        settle(s, held.reservation_id, line(units=0))
    assert snapshot(s) == before


def test_unused_expired_allocation_moves_to_expired_projection():
    s = MemorySession()
    held = reserve(s, estimate(units=10))
    receipt = settle(s, held.reservation_id, line(units=4), now=NOW + timedelta(days=30))
    grant = s.rows[CreditGrant][0]
    assert receipt.consumed_microcredits == 4_000 and receipt.released_microcredits == 6_000
    assert (grant.reserved_microcredits, grant.consumed_microcredits,
            grant.expired_microcredits) == (0, 4_000, 6_000)
    event = [row for row in s.rows[CreditLedgerEvent] if row.kind == "settle"][0]
    assert event.expired_delta == 6_000


def test_corrupt_projection_or_reservation_fails_closed():
    s = MemorySession()
    held = reserve(s, estimate(units=5))
    s.rows[CreditGrant][0].reserved_microcredits += 1
    with pytest.raises(accounting.CreditAccountingError, match="^credit_account_inconsistent$"):
        settle(s, held.reservation_id, line(units=2))
    s.rows[CreditGrant][0].reserved_microcredits -= 1
    s.rows[CreditReservationItem][0].quoted_microcredits += 1
    with pytest.raises(accounting.CreditAccountingError, match="^credit_account_inconsistent$"):
        settle(s, held.reservation_id, line(units=2))


def test_terminal_outer_rollback_removes_every_money_movement():
    s = MemorySession()
    held = reserve(s, estimate(units=5))
    before = snapshot(s)
    async def scenario():
        with pytest.raises(RuntimeError, match="rollback"):
            async with s.begin_nested():
                await accounting.settle(
                    s, user_id=UID, reservation_id=held.reservation_id,
                    usage=report(line(units=2)), delivery="delivered",
                    operation_key="terminal_1", now=NOW)
                raise RuntimeError("rollback")
    run(scenario())
    assert snapshot(s) == before


def test_suspended_user_can_finish_existing_hold():
    s = MemorySession()
    held = reserve(s, estimate(units=5))
    s.rows[User][0].status = "suspended"
    assert release(s, held.reservation_id).status == "released"
