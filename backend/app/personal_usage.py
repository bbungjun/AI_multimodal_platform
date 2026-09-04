"""Coherent owner-scoped Plan, Credit, concurrency and Usage read model."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.credit_lifecycle import CreditLifecycleError, ensure_cycle
from app.credit_models import CreditGrant, CreditReservation, CreditUsageRecord
from app.credit_policy import RATE_CARD_VERSION, plan_policy


_MAX_BIGINT = 2**63 - 1
PUBLIC_ERROR_CODES = frozenset({"usage_busy", "usage_unavailable"})
METER_UNITS = (
    ("gemini_input_token", "token"),
    ("gemini_output_token", "token"),
    ("imagen_fast_image", "image"),
    ("imagen_standard_image", "image"),
    ("imagen_ultra_image", "image"),
    ("veo_fast_ms", "millisecond"),
    ("veo_standard_ms", "millisecond"),
)
_METER_NAMES = frozenset(meter for meter, _ in METER_UNITS)
_BUSY_STATES = frozenset({"55P03", "40P01", "40001", "57014"})


class PersonalUsageError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class MeterUsageView:
    meter: str
    unit: str
    observed_units: int
    charged_microcredits: int


@dataclass(frozen=True)
class CycleUsageView:
    index: int
    starts_at: datetime
    renews_at: datetime
    allowance_microcredits: int
    charged_microcredits: int


@dataclass(frozen=True)
class CreditBalanceView:
    available_microcredits: int
    held_microcredits: int


@dataclass(frozen=True)
class ConcurrencyView:
    active_requests: int
    limit: int


@dataclass(frozen=True)
class PersonalUsageView:
    plan: str
    pending_plan: str | None
    rate_card_version: str
    cycle: CycleUsageView
    credit: CreditBalanceView
    concurrency: ConcurrencyView
    usage: tuple[MeterUsageView, ...]


def _instant(value: datetime) -> datetime:
    try:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise PersonalUsageError("usage_input_invalid") from None


def _integer(value: object) -> int:
    if type(value) is not int or value < 0 or value > _MAX_BIGINT:
        raise PersonalUsageError("usage_unavailable")
    return value


def _add(total: int, value: object) -> int:
    value = _integer(value)
    if total > _MAX_BIGINT - value:
        raise PersonalUsageError("usage_unavailable")
    return total + value


@asynccontextmanager
async def _transaction(session):
    if not session.in_transaction():
        raise PersonalUsageError("usage_transaction_required")
    try:
        async with session.begin_nested():
            yield
    except PersonalUsageError:
        raise
    except CreditLifecycleError as error:
        raise PersonalUsageError(
            "usage_busy" if error.code == "credit_busy" else "usage_unavailable"
        ) from None
    except DBAPIError as error:
        code = "usage_busy" if getattr(error.orig, "sqlstate", None) in _BUSY_STATES else "usage_unavailable"
        raise PersonalUsageError(code) from None


def _locked(model, *criteria):
    return (
        select(model)
        .where(*criteria)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def _all(session, statement):
    return list((await session.scalars(statement)).all())


def _grant_totals(grants) -> tuple[int, int]:
    available = 0
    held = 0
    for grant in grants:
        granted = _integer(grant.granted_microcredits)
        reserved = _integer(grant.reserved_microcredits)
        consumed = _integer(grant.consumed_microcredits)
        expired = _integer(grant.expired_microcredits)
        spent = _add(_add(reserved, consumed), expired)
        if spent > granted:
            raise PersonalUsageError("usage_unavailable")
        available = _add(available, granted - spent)
        held = _add(held, reserved)
    return available, held


def _reservation_totals(reservations) -> tuple[int, int]:
    held = 0
    for reservation in reservations:
        if reservation.status != "held":
            raise PersonalUsageError("usage_unavailable")
        held = _add(held, reservation.reserved_microcredits)
    return len(reservations), held


def _usage_totals(records) -> tuple[tuple[MeterUsageView, ...], int]:
    totals = {meter: [0, 0] for meter, _ in METER_UNITS}
    charged_total = 0
    for record in records:
        if (
            record.meter not in _METER_NAMES
            or record.rate_card_version != RATE_CARD_VERSION
            or record.delivery not in {"delivered", "partial", "no_deliverable"}
        ):
            raise PersonalUsageError("usage_unavailable")
        observed = _integer(record.actual_units)
        charged = _integer(record.charged_microcredits)
        if record.delivery == "no_deliverable" and charged != 0:
            raise PersonalUsageError("usage_unavailable")
        totals[record.meter][0] = _add(totals[record.meter][0], observed)
        totals[record.meter][1] = _add(totals[record.meter][1], charged)
        charged_total = _add(charged_total, charged)
    return tuple(
        MeterUsageView(meter, unit, totals[meter][0], totals[meter][1])
        for meter, unit in METER_UNITS
    ), charged_total


async def read_personal_usage(
    session,
    *,
    user_id: UUID,
    now: datetime,
) -> PersonalUsageView:
    if not isinstance(user_id, UUID):
        raise PersonalUsageError("usage_input_invalid")
    now = _instant(now)
    async with _transaction(session):
        cycle = await ensure_cycle(session, user_id=user_id, now=now)
        try:
            policy = plan_policy(cycle.plan)
        except ValueError:
            raise PersonalUsageError("usage_unavailable") from None

        grants = await _all(
            session,
            _locked(CreditGrant, CreditGrant.user_id == user_id).order_by(CreditGrant.id),
        )
        reservations = await _all(
            session,
            _locked(
                CreditReservation,
                CreditReservation.user_id == user_id,
                CreditReservation.status == "held",
            ).order_by(CreditReservation.created_at, CreditReservation.id),
        )
        records = await _all(
            session,
            _locked(
                CreditUsageRecord,
                CreditUsageRecord.user_id == user_id,
                CreditUsageRecord.recorded_at >= cycle.starts_at,
                CreditUsageRecord.recorded_at <= now,
            ).order_by(CreditUsageRecord.meter, CreditUsageRecord.reservation_id),
        )

        available, grant_held = _grant_totals(grants)
        active, reservation_held = _reservation_totals(reservations)
        if grant_held != reservation_held or active > policy.max_concurrent_requests:
            raise PersonalUsageError("usage_unavailable")
        usage, cycle_charged = _usage_totals(records)
        if (
            type(cycle.cycle_index) is not int
            or cycle.cycle_index < 0
            or cycle.starts_at > now
            or cycle.ends_at <= now
        ):
            raise PersonalUsageError("usage_unavailable")
        allowance = _integer(cycle.allowance_microcredits)

        return PersonalUsageView(
            plan=cycle.plan,
            pending_plan=cycle.pending_plan,
            rate_card_version=RATE_CARD_VERSION,
            cycle=CycleUsageView(
                index=cycle.cycle_index,
                starts_at=cycle.starts_at,
                renews_at=cycle.ends_at,
                allowance_microcredits=allowance,
                charged_microcredits=cycle_charged,
            ),
            credit=CreditBalanceView(available, grant_held),
            concurrency=ConcurrencyView(active, policy.max_concurrent_requests),
            usage=usage,
        )
