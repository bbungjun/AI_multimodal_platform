"""Atomic credit accounting behind a small caller-owned transaction Interface."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.credit_lifecycle import CreditLifecycleError, ensure_cycle
from app.credit_models import (
    CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent,
    CreditReservation, CreditReservationAllocation, CreditReservationItem,
    CreditUsageRecord,
)
from app.credit_policy import RATE_CARD_VERSION, plan_policy, quote_usage
from app.identity_models import User


__all__ = [
    "reserve", "settle", "release", "CreditAccountingError",
    "UsageEstimate", "ReservationRequest", "UsageLine", "UsageReport",
    "ReservationReceipt", "TerminalReceipt",
]

_MAX = 2**63 - 1
_KEY = re.compile(r"[A-Za-z0-9_-]{1,96}")
_METERS = frozenset({
    "gemini_input_token", "gemini_output_token", "imagen_fast_image",
    "imagen_standard_image", "imagen_ultra_image", "veo_fast_ms",
    "veo_standard_ms",
})
_SOURCES = frozenset({"provider_reported", "platform_measured", "mock_estimate", "estimated"})
_DELIVERIES = frozenset({"delivered", "partial"})
_REASONS = frozenset({
    "provider_failed", "provider_timeout", "provider_rate_limited",
    "cancelled_before_delivery", "delivery_failed",
})


class CreditAccountingError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class UsageEstimate:
    meter: str
    maximum_units: int


@dataclass(frozen=True)
class ReservationRequest:
    user_id: UUID
    operation_key: str
    estimates: tuple[UsageEstimate, ...]


@dataclass(frozen=True)
class UsageLine:
    meter: str
    actual_units: int
    source: str


@dataclass(frozen=True)
class UsageReport:
    lines: tuple[UsageLine, ...]


@dataclass(frozen=True)
class ReservationReceipt:
    reservation_id: UUID
    operation_key: str
    status: str
    reserved_microcredits: int
    rate_card_version: str
    replayed: bool


@dataclass(frozen=True)
class TerminalReceipt:
    reservation_id: UUID
    operation_key: str
    status: str
    consumed_microcredits: int
    released_microcredits: int
    usage_line_count: int
    effective_at: datetime
    replayed: bool


def _fail(code: str = "credit_input_invalid"):
    raise CreditAccountingError(code)


def _instant(value) -> datetime:
    try:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            _fail()
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        _fail()


def _uuid(value) -> UUID:
    if not isinstance(value, UUID):
        _fail()
    return value


def _key(value) -> str:
    if type(value) is not str or _KEY.fullmatch(value) is None:
        _fail()
    return value


def _units(value, *, positive: bool) -> int:
    if type(value) is not int or value < (1 if positive else 0) or value > _MAX:
        _fail()
    return value


def _amount(value) -> int:
    if type(value) is not int or not 0 <= value <= _MAX:
        _fail("credit_account_inconsistent")
    return value


def _sum_amounts(values, *, positive=False) -> int:
    total = 0
    for value in values:
        total += _amount(value)
        if total > _MAX:
            _fail("credit_amount_overflow")
    if positive and total <= 0:
        _fail("credit_input_invalid")
    return total


def _estimates(value) -> tuple[UsageEstimate, ...]:
    if type(value) is not tuple or not 1 <= len(value) <= len(_METERS):
        _fail()
    normalized = []
    seen = set()
    for line in value:
        if not isinstance(line, UsageEstimate) or type(line.meter) is not str or line.meter not in _METERS:
            _fail()
        if line.meter in seen:
            _fail()
        seen.add(line.meter)
        normalized.append(UsageEstimate(line.meter, _units(line.maximum_units, positive=True)))
    return tuple(sorted(normalized, key=lambda line: line.meter))


def _usage(value, *, allow_empty: bool) -> tuple[UsageLine, ...]:
    if type(value) is not UsageReport or type(value.lines) is not tuple:
        _fail()
    if (not allow_empty and not value.lines) or len(value.lines) > len(_METERS):
        _fail()
    normalized = []
    seen = set()
    for line in value.lines:
        if (not isinstance(line, UsageLine) or type(line.meter) is not str
                or line.meter not in _METERS or type(line.source) is not str
                or line.source not in _SOURCES or line.meter in seen):
            _fail()
        seen.add(line.meter)
        normalized.append(UsageLine(line.meter, _units(line.actual_units, positive=False), line.source))
    return tuple(sorted(normalized, key=lambda line: line.meter))


@asynccontextmanager
async def _transaction(session):
    if not session.in_transaction():
        raise CreditAccountingError("credit_transaction_required")
    try:
        async with session.begin_nested():
            yield
    except CreditAccountingError:
        raise
    except DBAPIError as error:
        state = getattr(error.orig, "sqlstate", None)
        code = "credit_busy" if state in {"55P03", "40P01", "40001", "57014"} else "credit_account_inconsistent"
        raise CreditAccountingError(code) from None


def _locked(model, *criteria):
    return select(model).where(*criteria).with_for_update().execution_options(populate_existing=True)


def _lifecycle_error(error: CreditLifecycleError):
    code = error.code
    if code == "credit_clock_regressed":
        code = "credit_account_inconsistent"
    if code not in {
        "credit_transaction_required", "credit_user_missing", "credit_input_invalid",
        "credit_plan_refused", "credit_account_inconsistent", "credit_amount_overflow",
        "credit_busy",
    }:
        code = "credit_account_inconsistent"
    raise CreditAccountingError(code) from None


async def _ledger_coherent(session, user_id, grants):
    events = list((await session.scalars(select(CreditLedgerEvent).where(
        CreditLedgerEvent.user_id == user_id).order_by(CreditLedgerEvent.created_at, CreditLedgerEvent.id))).all())
    totals = {grant.id: [0, 0, 0, 0] for grant in grants}
    for event in events:
        if event.grant_id not in totals:
            _fail("credit_account_inconsistent")
        for index, name in enumerate(("granted_delta", "reserved_delta", "consumed_delta", "expired_delta")):
            value = getattr(event, name)
            if type(value) is not int:
                _fail("credit_account_inconsistent")
            totals[event.grant_id][index] += value
            if not -_MAX <= totals[event.grant_id][index] <= _MAX:
                _fail("credit_amount_overflow")
    for grant in grants:
        actual = tuple(_amount(getattr(grant, name)) for name in (
            "granted_microcredits", "reserved_microcredits",
            "consumed_microcredits", "expired_microcredits"))
        if tuple(totals[grant.id]) != actual or sum(actual[1:]) > actual[0]:
            _fail("credit_account_inconsistent")


async def _reservation_items(session, reservation_id):
    return tuple((await session.scalars(_locked(
        CreditReservationItem, CreditReservationItem.reservation_id == reservation_id)
        .order_by(CreditReservationItem.meter))).all())


def _reservation_receipt(reservation, *, replayed):
    return ReservationReceipt(
        reservation.id, reservation.reserve_operation_key, "held",
        reservation.reserved_microcredits, reservation.rate_card_version, replayed,
    )


async def reserve(session, *, request, now) -> ReservationReceipt:
    if not isinstance(request, ReservationRequest):
        _fail()
    normalized = ReservationRequest(_uuid(request.user_id), _key(request.operation_key), _estimates(request.estimates))
    instant = _instant(now)
    async with _transaction(session):
        return await _reserve(session, normalized, instant)


async def settle(session, *, user_id, reservation_id, usage, delivery,
                 operation_key, now) -> TerminalReceipt:
    uid, rid, key, instant = _uuid(user_id), _uuid(reservation_id), _key(operation_key), _instant(now)
    lines = _usage(usage, allow_empty=False)
    if type(delivery) is not str or delivery not in _DELIVERIES:
        _fail()
    async with _transaction(session):
        return await _terminal(session, uid, rid, lines, delivery, "usage_settled", key, instant, True)


async def release(session, *, user_id, reservation_id, usage, reason_code,
                  operation_key, now) -> TerminalReceipt:
    uid, rid, key, instant = _uuid(user_id), _uuid(reservation_id), _key(operation_key), _instant(now)
    lines = _usage(usage, allow_empty=True)
    if type(reason_code) is not str or reason_code not in _REASONS:
        _fail()
    async with _transaction(session):
        return await _terminal(session, uid, rid, lines, "no_deliverable", reason_code, key, instant, False)


async def _reserve(session, request, now):
    user = await session.scalar(_locked(User, User.id == request.user_id))
    if user is None:
        _fail("credit_user_missing")
    if now < user.signed_up_at:
        _fail()

    existing = await session.scalar(_locked(
        CreditReservation, CreditReservation.user_id == request.user_id,
        CreditReservation.reserve_operation_key == request.operation_key))
    if existing is not None:
        items = await _reservation_items(session, existing.id)
        stored = tuple((item.meter, item.maximum_units) for item in items)
        supplied = tuple((item.meter, item.maximum_units) for item in request.estimates)
        if stored != supplied:
            _fail("credit_idempotency_conflict")
        return _reservation_receipt(existing, replayed=True)

    if user.status == "suspended":
        _fail("credit_plan_refused")
    try:
        view = await ensure_cycle(session, user_id=request.user_id, now=now)
    except CreditLifecycleError as error:
        _lifecycle_error(error)

    account = await session.scalar(_locked(CreditAccount, CreditAccount.user_id == request.user_id))
    cycle = await session.scalar(_locked(CreditCycle, CreditCycle.id == view.cycle_id,
                                         CreditCycle.user_id == request.user_id))
    grants = list((await session.scalars(_locked(CreditGrant, CreditGrant.user_id == request.user_id)
                                        .order_by(CreditGrant.id))).all())
    if account is None or cycle is None or account.plan != view.plan:
        _fail("credit_account_inconsistent")
    try:
        policy = plan_policy(account.plan)
    except ValueError:
        _fail("credit_account_inconsistent")
    if any(item.meter not in policy.permitted_meters for item in request.estimates):
        _fail("credit_plan_refused")

    await session.flush()
    await _ledger_coherent(session, request.user_id, grants)
    quoted = []
    try:
        for item in request.estimates:
            quoted.append((item, quote_usage(
                version=RATE_CARD_VERSION, meter=item.meter, units=item.maximum_units)))
    except ValueError as error:
        code = "credit_amount_overflow" if str(error) == "credit_amount_overflow" else "credit_input_invalid"
        _fail(code)
    total = _sum_amounts((amount for _, amount in quoted), positive=True)

    priority = sorted(grants, key=lambda grant: (
        grant.expires_at is None,
        grant.expires_at or datetime.max.replace(tzinfo=timezone.utc),
        grant.created_at,
        grant.id,
    ))
    remaining = total
    allocations = []
    for grant in priority:
        available = _amount(grant.granted_microcredits) - _amount(grant.reserved_microcredits) \
            - _amount(grant.consumed_microcredits) - _amount(grant.expired_microcredits)
        if available < 0:
            _fail("credit_account_inconsistent")
        taken = min(available, remaining)
        if taken:
            allocations.append((grant, taken))
            remaining -= taken
        if remaining == 0:
            break
    if remaining:
        _fail("monthly_credit_exhausted")

    reservation = CreditReservation(
        id=uuid4(), user_id=request.user_id, reserve_operation_key=request.operation_key,
        rate_card_version=RATE_CARD_VERSION, status="held", reserved_microcredits=total,
        created_at=now, terminal_operation_key=None, terminal_at=None,
        terminal_reason_code=None, delivery=None,
    )
    session.add(reservation)
    for item, amount in quoted:
        session.add(CreditReservationItem(
            reservation_id=reservation.id, user_id=request.user_id, meter=item.meter,
            maximum_units=item.maximum_units, quoted_microcredits=amount,
        ))
    for ordinal, (grant, amount) in enumerate(allocations):
        session.add(CreditReservationAllocation(
            reservation_id=reservation.id, grant_id=grant.id, user_id=request.user_id,
            ordinal=ordinal, reserved_microcredits=amount,
        ))
        grant.reserved_microcredits += amount
        session.add(CreditLedgerEvent(
            id=uuid4(), user_id=request.user_id, grant_id=grant.id, kind="reserve",
            operation_key="reserve_" + reservation.id.hex,
            rate_card_version=RATE_CARD_VERSION, granted_delta=0,
            reserved_delta=amount, consumed_delta=0, expired_delta=0,
            created_at=now, reason_code="credit_reserved",
        ))
    await session.flush()
    return _reservation_receipt(reservation, replayed=False)


async def _terminal(session, user_id, reservation_id, lines, delivery, reason, key, now, charge):
    user = await session.scalar(_locked(User, User.id == user_id))
    if user is None:
        _fail("credit_user_missing")
    account = await session.scalar(_locked(CreditAccount, CreditAccount.user_id == user_id))
    cycle = await session.scalar(_locked(CreditCycle, CreditCycle.user_id == user_id)
                                 .order_by(CreditCycle.cycle_index.desc()).limit(1))
    grants = list((await session.scalars(_locked(CreditGrant, CreditGrant.user_id == user_id)
                                        .order_by(CreditGrant.id))).all())
    if account is None or cycle is None or now < account.updated_at:
        _fail("credit_account_inconsistent")
    await _ledger_coherent(session, user_id, grants)

    replay = await session.scalar(_locked(
        CreditReservation, CreditReservation.user_id == user_id,
        CreditReservation.terminal_operation_key == key))
    if replay is not None:
        items = await _reservation_items(session, replay.id)
        allocations = tuple((await session.scalars(_locked(
            CreditReservationAllocation,
            CreditReservationAllocation.reservation_id == replay.id)
            .order_by(CreditReservationAllocation.ordinal))).all())
        records = tuple((await session.scalars(_locked(
            CreditUsageRecord, CreditUsageRecord.reservation_id == replay.id)
            .order_by(CreditUsageRecord.meter))).all())
        _reservation_coherent(replay, items, allocations, grants)
        expected_status = "settled" if charge else "released"
        supplied = tuple((line.meter, line.actual_units, line.source) for line in lines)
        stored = tuple((row.meter, row.actual_units, row.source) for row in records)
        if (replay.id != reservation_id or replay.status != expected_status
                or replay.delivery != delivery or replay.terminal_reason_code != reason
                or supplied != stored):
            _fail("credit_idempotency_conflict")
        return _terminal_receipt(replay, records, replayed=True)

    reservation = await session.scalar(_locked(
        CreditReservation, CreditReservation.id == reservation_id,
        CreditReservation.user_id == user_id))
    if reservation is None:
        _fail("credit_reservation_missing")
    items = await _reservation_items(session, reservation.id)
    allocations = tuple((await session.scalars(_locked(
        CreditReservationAllocation,
        CreditReservationAllocation.reservation_id == reservation.id)
        .order_by(CreditReservationAllocation.ordinal))).all())
    _reservation_coherent(reservation, items, allocations, grants)
    if reservation.status != "held":
        _fail("credit_reservation_state_conflict")
    if now < reservation.created_at:
        _fail()

    by_meter = {item.meter: item for item in items}
    if any(line.meter not in by_meter for line in lines):
        _fail("credit_usage_exceeds_reservation")
    charges = {}
    try:
        for line in lines:
            item = by_meter[line.meter]
            if line.actual_units > item.maximum_units:
                _fail("credit_usage_exceeds_reservation")
            charges[line.meter] = quote_usage(
                version=reservation.rate_card_version,
                meter=line.meter,
                units=line.actual_units,
            ) if charge else 0
    except CreditAccountingError:
        raise
    except ValueError as error:
        code = "credit_amount_overflow" if str(error) == "credit_amount_overflow" else "credit_account_inconsistent"
        _fail(code)
    consumed = _sum_amounts(charges.values())
    if charge and consumed <= 0:
        _fail("credit_input_invalid")
    if consumed > reservation.reserved_microcredits:
        _fail("credit_usage_exceeds_reservation")

    grants_by_id = {grant.id: grant for grant in grants}
    remaining = consumed
    event_kind = "settle" if charge else "release"
    for allocation in allocations:
        grant = grants_by_id[allocation.grant_id]
        held = allocation.reserved_microcredits
        spent = min(held, remaining)
        remaining -= spent
        unused = held - spent
        expired = unused if grant.expires_at is not None and grant.expires_at <= now else 0
        if grant.reserved_microcredits < held:
            _fail("credit_account_inconsistent")
        grant.reserved_microcredits -= held
        grant.consumed_microcredits += spent
        grant.expired_microcredits += expired
        if any(value > _MAX for value in (
                grant.consumed_microcredits, grant.expired_microcredits)):
            _fail("credit_amount_overflow")
        session.add(CreditLedgerEvent(
            id=uuid4(), user_id=user_id, grant_id=grant.id, kind=event_kind,
            operation_key="terminal_" + reservation.id.hex,
            rate_card_version=reservation.rate_card_version,
            granted_delta=0, reserved_delta=-held, consumed_delta=spent,
            expired_delta=expired, created_at=now, reason_code=reason,
        ))
    if remaining:
        _fail("credit_account_inconsistent")

    for line in lines:
        session.add(CreditUsageRecord(
            reservation_id=reservation.id, meter=line.meter, user_id=user_id,
            terminal_operation_key=key, rate_card_version=reservation.rate_card_version,
            actual_units=line.actual_units, charged_microcredits=charges[line.meter],
            recorded_at=now, source=line.source, delivery=delivery,
        ))
    reservation.status = "settled" if charge else "released"
    reservation.terminal_operation_key = key
    reservation.terminal_at = now
    reservation.terminal_reason_code = reason
    reservation.delivery = delivery
    await session.flush()
    records = tuple(sorted((row for row in getattr(session, "new", ())
                            if isinstance(row, CreditUsageRecord)
                            and row.reservation_id == reservation.id), key=lambda row: row.meter))
    if not records:
        # Fakes do not expose AsyncSession.new; the normalized inputs are equivalent.
        records = tuple(CreditUsageRecord(
            reservation_id=reservation.id, meter=line.meter, user_id=user_id,
            terminal_operation_key=key, rate_card_version=reservation.rate_card_version,
            actual_units=line.actual_units, charged_microcredits=charges[line.meter],
            recorded_at=now, source=line.source, delivery=delivery,
        ) for line in lines)
    return _terminal_receipt(reservation, records, replayed=False)


def _reservation_coherent(reservation, items, allocations, grants):
    try:
        item_total = _sum_amounts(item.quoted_microcredits for item in items)
        allocation_total = _sum_amounts(allocation.reserved_microcredits for allocation in allocations)
        if (not items or not allocations or item_total != reservation.reserved_microcredits
                or allocation_total != reservation.reserved_microcredits):
            _fail("credit_account_inconsistent")
        grant_ids = {grant.id for grant in grants}
        if any(allocation.user_id != reservation.user_id or allocation.grant_id not in grant_ids
               for allocation in allocations):
            _fail("credit_account_inconsistent")
        for item in items:
            expected = quote_usage(version=reservation.rate_card_version,
                                   meter=item.meter, units=item.maximum_units)
            if item.user_id != reservation.user_id or item.quoted_microcredits != expected:
                _fail("credit_account_inconsistent")
    except ValueError:
        _fail("credit_account_inconsistent")


def _terminal_receipt(reservation, records, *, replayed):
    consumed = _sum_amounts(row.charged_microcredits for row in records)
    released = reservation.reserved_microcredits - consumed
    if released < 0 or reservation.terminal_at is None:
        _fail("credit_account_inconsistent")
    return TerminalReceipt(
        reservation.id, reservation.terminal_operation_key, reservation.status,
        consumed, released, len(records), reservation.terminal_at, replayed,
    )
