"""Transaction-composable credit lifecycle. No product callers or provider work."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.credit_models import CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent, CreditOperation
from app.credit_policy import RATE_CARD_VERSION, cycle_bounds, plan_policy
from app.identity_models import User

_MAX = 2**63 - 1
_RANK = {"free": 0, "pro": 1, "max": 2}


class CreditLifecycleError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CycleView:
    user_id: UUID
    plan: str
    pending_plan: str | None
    cycle_id: UUID
    cycle_index: int
    starts_at: datetime
    ends_at: datetime
    allowance_microcredits: int
    base_grant_id: UUID


@dataclass(frozen=True)
class MutationReceipt:
    operation_key: str
    kind: str
    outcome: str
    effective_at: datetime
    cycle_id: UUID
    grant_id: UUID | None
    replayed: bool


def _instant(value):
    try:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise CreditLifecycleError("credit_input_invalid") from None


def _inputs(user_id, now):
    if not isinstance(user_id, UUID):
        raise CreditLifecycleError("credit_input_invalid")
    return _instant(now)


@asynccontextmanager
async def _transaction(session):
    if not session.in_transaction():
        raise CreditLifecycleError("credit_transaction_required")
    try:
        async with session.begin_nested():
            yield
    except DBAPIError as error:
        state = getattr(error.orig, "sqlstate", None)
        code = "credit_busy" if state in {"55P03", "40P01", "40001", "57014"} else "credit_account_inconsistent"
        raise CreditLifecycleError(code) from None


def _locked(model, *criteria):
    return select(model).where(*criteria).with_for_update().execution_options(populate_existing=True)


async def _load(session, user_id, now):
    user = await session.scalar(_locked(User, User.id == user_id))
    if user is None:
        raise CreditLifecycleError("credit_user_missing")
    if now < user.signed_up_at:
        raise CreditLifecycleError("credit_input_invalid")
    account = await session.scalar(_locked(CreditAccount, CreditAccount.user_id == user_id))
    return user, account


def _event(session, grant, kind, key, now, reason, **deltas):
    session.add(CreditLedgerEvent(
        id=uuid4(), user_id=grant.user_id, grant_id=grant.id, kind=kind,
        operation_key=key, rate_card_version=RATE_CARD_VERSION,
        created_at=now, reason_code=reason,
        **{name + "_delta": deltas.get(name, 0) for name in ("granted", "reserved", "consumed", "expired")}))


def _capacity(grants, increment=0):
    outstanding = sum(g.granted_microcredits - g.consumed_microcredits - g.expired_microcredits for g in grants)
    if outstanding < 0 or increment < 0 or outstanding + increment > _MAX:
        raise CreditLifecycleError("credit_amount_overflow")


def _coherent(user, account, cycle, grants):
    if (account.cycle_anchor_at != user.signed_up_at or account.plan not in _RANK
            or (account.pending_plan is not None and
                (account.pending_plan not in _RANK or _RANK[account.pending_plan] >= _RANK[account.plan]))
            or (user.role == "master" and (account.plan != "max" or account.pending_plan is not None))):
        raise CreditLifecycleError("credit_account_inconsistent")
    if cycle is None:
        raise CreditLifecycleError("credit_account_inconsistent")
    try:
        bounds = cycle_bounds(signed_up_at=user.signed_up_at, now=cycle.starts_at)
        expected = plan_policy(account.plan).allowance_microcredits
    except ValueError:
        raise CreditLifecycleError("credit_account_inconsistent") from None
    bases = [g for g in grants if g.kind == "base" and g.cycle_id == cycle.id]
    if (bounds.index != cycle.cycle_index or bounds.starts_at != cycle.starts_at
            or bounds.ends_at != cycle.ends_at or cycle.plan != account.plan
            or cycle.allowance_microcredits != expected or len(bases) != 1
            or bases[0].expires_at != cycle.ends_at
            or bases[0].granted_microcredits != expected):
        raise CreditLifecycleError("credit_account_inconsistent")
    return bases[0]


async def _ensure(session, user, account, now):
    try:
        bounds = cycle_bounds(signed_up_at=user.signed_up_at, now=now)
    except ValueError:
        raise CreditLifecycleError("credit_input_invalid") from None
    new = account is None
    if new:
        account = CreditAccount(user_id=user.id, cycle_anchor_at=user.signed_up_at,
                                plan="max" if user.role == "master" else "free",
                                pending_plan=None, created_at=now, updated_at=now)
        session.add(account)
        await session.flush()
    elif now < account.updated_at:
        raise CreditLifecycleError("credit_clock_regressed")
    cycle = await session.scalar(_locked(CreditCycle, CreditCycle.user_id == user.id)
                                 .order_by(CreditCycle.cycle_index.desc()).limit(1))
    grants = list((await session.scalars(_locked(CreditGrant, CreditGrant.user_id == user.id)
                                        .order_by(CreditGrant.id))).all())
    base = None
    if not new:
        base = _coherent(user, account, cycle, grants)
        if cycle.cycle_index > bounds.index:
            raise CreditLifecycleError("credit_clock_regressed")
    elif cycle is not None or grants:
        raise CreditLifecycleError("credit_account_inconsistent")
    for grant in grants:
        available = grant.available_microcredits
        if available < 0:
            raise CreditLifecycleError("credit_account_inconsistent")
        if grant.expires_at is not None and grant.expires_at <= now and available:
            grant.expired_microcredits += available
            _event(session, grant, "expire", "expire_" + grant.id.hex, now, "grant_expired", expired=available)
    if cycle is None or cycle.cycle_index < bounds.index:
        if account.pending_plan is not None:
            account.plan, account.pending_plan = account.pending_plan, None
        allowance = plan_policy(account.plan).allowance_microcredits
        _capacity(grants, allowance)
        cycle = CreditCycle(id=uuid4(), user_id=user.id, cycle_index=bounds.index,
                            starts_at=bounds.starts_at, ends_at=bounds.ends_at,
                            plan=account.plan, allowance_microcredits=allowance, created_at=now)
        session.add(cycle)
        await session.flush()
        base = CreditGrant(id=uuid4(), user_id=user.id, cycle_id=cycle.id, kind="base",
                           created_at=now, expires_at=bounds.ends_at, reason_code="cycle_base",
                           granted_microcredits=allowance, reserved_microcredits=0,
                           consumed_microcredits=0, expired_microcredits=0)
        session.add(base)
        await session.flush()
        grants.append(base)
        _event(session, base, "grant", "cycle_" + str(bounds.index) + "_base", now, "cycle_base", granted=allowance)
    _capacity(grants)
    account.updated_at = now
    await session.flush()
    return account, cycle, base, grants


def _view(account, cycle, base):
    return CycleView(account.user_id, account.plan, account.pending_plan, cycle.id,
                     cycle.cycle_index, cycle.starts_at, cycle.ends_at,
                     cycle.allowance_microcredits, base.id)


async def ensure_cycle(session, *, user_id, now):
    now = _inputs(user_id, now)
    async with _transaction(session):
        user, account = await _load(session, user_id, now)
        account, cycle, base, _ = await _ensure(session, user, account, now)
        return _view(account, cycle, base)
