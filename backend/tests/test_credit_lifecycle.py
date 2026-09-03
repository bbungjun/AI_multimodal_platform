"""Unit fakes exercise the lifecycle Interface; PostgreSQL proof is separate."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.credit_lifecycle import CreditLifecycleError, ensure_cycle, change_plan, grant_bonus
from app.credit_models import CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent, CreditOperation
from app.identity_models import User

NOW = datetime(2024, 2, 29, 10, 30, 0, 123456, tzinfo=timezone.utc)
DAY30 = timedelta(days=30)
UID = UUID(int=1)


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class MemorySession:
    """Only statement/value contract fake; does not pretend to implement SQL locks."""
    def __init__(self, *, role="user", status="active", active=True):
        self.rows = {User: [User(id=UID, role=role, status=status, signed_up_at=NOW)]}
        self.active = active
        self.statements = []
        self.flushes = 0

    def in_transaction(self):
        return self.active

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
        self.flushes += 1

    def select(self, statement):
        self.statements.append(statement)
        model = statement.column_descriptions[0]["entity"]
        rows = list(self.rows.get(model, []))
        for criterion in statement._where_criteria:
            rows = [r for r in rows if getattr(r, criterion.left.key) == criterion.right.value]
        if model is CreditCycle:
            rows.sort(key=lambda r: r.cycle_index, reverse=True)
        if model is CreditGrant:
            rows.sort(key=lambda r: r.id)
        return rows

    async def scalar(self, statement):
        rows = self.select(statement)
        return rows[0] if rows else None

    async def scalars(self, statement):
        return Rows(self.select(statement))


def run(call):
    return asyncio.run(call)


def ensure(s, now=NOW):
    return run(ensure_cycle(s, user_id=UID, now=now))


@pytest.mark.parametrize("role,plan,credits", [("user", "free", 1000), ("master", "max", 50000)])
def test_initialization_has_one_base_and_immutable_view(role, plan, credits):
    s = MemorySession(role=role)
    view = ensure(s)
    assert view.plan == plan and view.allowance_microcredits == credits * 1_000_000
    assert view.starts_at == NOW and view.ends_at == NOW + DAY30
    assert ensure(s) == view
    for cls in (CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent):
        assert len(s.rows[cls]) == 1
    event = s.rows[CreditLedgerEvent][0]
    assert event.granted_delta == credits * 1_000_000 and event.operation_key == "cycle_0_base"
    with pytest.raises(FrozenInstanceError):
        view.plan = "max"
    assert all(st._for_update_arg is not None for st in s.statements)
    assert all(st.get_execution_options()["populate_existing"] for st in s.statements)


@pytest.mark.parametrize("index", [1, 2, 100])
def test_late_initialization_never_accumulates_skipped_cycles(index):
    s = MemorySession()
    view = ensure(s, NOW + index * DAY30 + timedelta(seconds=1))
    assert view.cycle_index == index and len(s.rows[CreditCycle]) == 1
    assert view.allowance_microcredits == 1_000_000_000


def test_renewal_half_open_expiry_preserves_held_and_consumed():
    s = MemorySession()
    first = ensure(s)
    grant = s.rows[CreditGrant][0]
    grant.reserved_microcredits = 20
    grant.consumed_microcredits = 30
    before = ensure(s, NOW + DAY30 - timedelta(microseconds=1))
    assert before.cycle_id == first.cycle_id
    next_view = ensure(s, NOW + DAY30)
    assert next_view.cycle_index == 1 and next_view.cycle_id != first.cycle_id
    assert (grant.reserved_microcredits, grant.consumed_microcredits, grant.expired_microcredits) == (20, 30, 999_999_950)
    assert grant.available_microcredits == 0
    assert len(s.rows[CreditLedgerEvent]) == 3
    ensure(s, NOW + DAY30)
    assert len(s.rows[CreditLedgerEvent]) == 3


def test_pending_downgrade_applies_once_after_skipped_cycles():
    s = MemorySession(role="master")
    ensure(s)
    s.rows[User][0].role = "user"
    s.rows[CreditAccount][0].pending_plan = "pro"
    view = ensure(s, NOW + 7 * DAY30)
    assert view.plan == "pro" and view.pending_plan is None and view.cycle_index == 7
    assert len(s.rows[CreditCycle]) == 2
    assert view.allowance_microcredits == 10_000_000_000


@pytest.mark.parametrize("active", [False])
def test_transaction_required_without_side_effect(active):
    s = MemorySession(active=active)
    with pytest.raises(CreditLifecycleError, match="^credit_transaction_required$"):
        ensure(s)
    assert set(s.rows) == {User}


@pytest.mark.parametrize("change", ["anchor", "allowance", "base", "master"])
def test_incoherent_existing_account_fails_closed(change):
    s = MemorySession()
    ensure(s)
    if change == "anchor":
        s.rows[CreditAccount][0].cycle_anchor_at -= timedelta(seconds=1)
    elif change == "allowance":
        s.rows[CreditCycle][0].allowance_microcredits += 1
    elif change == "base":
        s.rows[CreditGrant].clear()
    else:
        s.rows[User][0].role = "master"
    with pytest.raises(CreditLifecycleError, match="^credit_account_inconsistent$"):
        ensure(s, NOW + DAY30)


@pytest.mark.parametrize("now", [NOW.replace(tzinfo=None), NOW - timedelta(microseconds=1), "not_time"])
def test_invalid_time_does_not_create_account(now):
    s = MemorySession()
    with pytest.raises(CreditLifecycleError, match="^credit_input_invalid$"):
        ensure(s, now)
    assert set(s.rows) == {User}


def test_clock_regression_and_missing_user():
    s = MemorySession()
    ensure(s, NOW + timedelta(seconds=2))
    with pytest.raises(CreditLifecycleError, match="^credit_clock_regressed$"):
        ensure(s, NOW + timedelta(seconds=1))
    with pytest.raises(CreditLifecycleError, match="^credit_user_missing$"):
        run(ensure_cycle(s, user_id=UUID(int=999), now=NOW))


def test_suspended_ensure_is_accounting_only_and_outer_rollback():
    s = MemorySession(status="suspended")
    async def scenario():
        with pytest.raises(RuntimeError, match="rollback"):
            async with s.begin_nested():
                await ensure_cycle(s, user_id=UID, now=NOW)
                raise RuntimeError("rollback")
        assert set(s.rows) == {User}
    run(scenario())
    assert ensure(s).plan == "free"
    assert s.rows[User][0].status == "suspended"


def change(s, plan, key="plan", now=NOW):
    return run(change_plan(s, user_id=UID, target_plan=plan, operation_key=key, now=now))


def bonus(s, key="bonus", now=NOW, **extra):
    values = dict(amount_microcredits=100, expires_at=None, reason_code="support")
    values.update(extra)
    return run(grant_bonus(s, user_id=UID, operation_key=key, now=now, **values))


@pytest.mark.parametrize("current", ["free", "pro", "max"])
@pytest.mark.parametrize("target", ["free", "pro", "max"])
def test_all_plan_pairs_preserve_consumed_and_held(current, target):
    s = MemorySession()
    ensure(s)
    change(s, current, "setup")
    base = s.rows[CreditGrant][0]
    base.consumed_microcredits, base.reserved_microcredits, base.expired_microcredits = 10, 20, 30
    old = base.granted_microcredits
    ledger_count = len(s.rows[CreditLedgerEvent])
    receipt = change(s, target)
    account = s.rows[CreditAccount][0]
    rank = {"free": 0, "pro": 1, "max": 2}
    if rank[target] > rank[current]:
        assert account.plan == target and account.pending_plan is None
        assert receipt.outcome == "upgraded" and len(s.rows[CreditLedgerEvent]) == ledger_count + 1
        assert base.granted_microcredits > old
    elif rank[target] < rank[current]:
        assert account.plan == current and account.pending_plan == target
        assert receipt.outcome == "scheduled" and len(s.rows[CreditLedgerEvent]) == ledger_count
        assert base.granted_microcredits == old
    else:
        assert receipt.outcome == "unchanged" and base.granted_microcredits == old
    assert (base.consumed_microcredits, base.reserved_microcredits, base.expired_microcredits) == (10, 20, 30)


def test_pending_replace_cancel_and_same_pending_noop():
    s = MemorySession()
    change(s, "max", "upgrade")
    assert change(s, "pro", "lower").outcome == "scheduled"
    assert change(s, "free", "replace").outcome == "scheduled"
    assert change(s, "free", "same").outcome == "unchanged"
    assert change(s, "max", "cancel").outcome == "cancelled"
    assert s.rows[CreditAccount][0].pending_plan is None
    assert len(s.rows[CreditOperation]) == 5


def test_replay_before_renewal_has_no_side_effects_even_suspended():
    s = MemorySession()
    original = change(s, "pro")
    before = snapshot(s)
    s.rows[User][0].status = "suspended"
    replay = change(s, "pro", now=NOW + 9 * DAY30)
    assert replay.replayed and replay.effective_at == original.effective_at
    assert replay.cycle_id == original.cycle_id and replay.grant_id == original.grant_id
    assert snapshot(s) == before
    with pytest.raises(CreditLifecycleError, match="credit_plan_refused"):
        change(s, "max", "new", NOW + DAY30)


def snapshot(s):
    return {cls: [tuple(getattr(row, col.name) for col in cls.__table__.columns)
                  for row in s.rows.get(cls, [])]
            for cls in (CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent, CreditOperation)}


@pytest.mark.parametrize("field,value", [
    ("amount_microcredits", 101), ("expires_at", NOW + DAY30),
    ("reason_code", "different")])
def test_bonus_payload_collision_before_renewal_is_atomic(field, value):
    s = MemorySession()
    bonus(s)
    before = snapshot(s)
    with pytest.raises(CreditLifecycleError, match="credit_idempotency_conflict"):
        bonus(s, now=NOW + 8 * DAY30, **{field: value})
    assert snapshot(s) == before


def test_cross_kind_and_plan_target_collisions():
    s = MemorySession()
    change(s, "free", "same")
    before = snapshot(s)
    for call in (lambda: change(s, "pro", "same", NOW + DAY30),
                 lambda: bonus(s, key="same", now=NOW + DAY30)):
        with pytest.raises(CreditLifecycleError, match="credit_idempotency_conflict"):
            call()
        assert snapshot(s) == before


def test_finite_bonus_expiry_and_replay_never_regrant():
    s = MemorySession()
    expiry = NOW + timedelta(seconds=10)
    first = bonus(s, expires_at=expiry)
    ensure(s, expiry)
    before = snapshot(s)
    replay = bonus(s, expires_at=expiry, now=expiry + DAY30)
    assert replay.replayed and replay.grant_id == first.grant_id
    assert snapshot(s) == before
    grant = next(g for g in s.rows[CreditGrant] if g.id == first.grant_id)
    assert grant.available_microcredits == 0 and grant.expired_microcredits == 100


@pytest.mark.parametrize("amount", [True, 1.0, "1", 0, -1, 2**63])
def test_invalid_bonus_rejected_without_account(amount):
    s = MemorySession()
    with pytest.raises(CreditLifecycleError, match="credit_input_invalid"):
        bonus(s, amount_microcredits=amount)
    assert set(s.rows) == {User}


@pytest.mark.parametrize("key", ["", "a" * 97, "unsafe space", "new\nline", None])
def test_unsafe_keys_rejected(key):
    s = MemorySession()
    with pytest.raises(CreditLifecycleError, match="credit_input_invalid"):
        bonus(s, key=key)
    assert set(s.rows) == {User}


def test_outstanding_overflow_rolls_back_initial_cycle_and_bonus():
    s = MemorySession()
    with pytest.raises(CreditLifecycleError, match="credit_amount_overflow"):
        bonus(s, amount_microcredits=2**63 - 1)
    assert set(s.rows) == {User}


def test_master_rejection_and_boundary_new_intent():
    s = MemorySession(role="master")
    with pytest.raises(CreditLifecycleError, match="credit_plan_refused"):
        change(s, "pro")
    assert set(s.rows) == {User}
    s = MemorySession()
    change(s, "pro", "up")
    change(s, "free", "down")
    receipt = change(s, "pro", "new", NOW + DAY30)
    assert receipt.outcome == "upgraded"
    assert len(s.rows[CreditCycle]) == 2
    assert s.rows[CreditAccount][0].plan == "pro"
    assert len(s.rows[CreditGrant]) == 2


def test_database_contention_is_sanitized_and_savepoint_rolled_back():
    from sqlalchemy.exc import DBAPIError
    s = MemorySession()
    async def failed_flush():
        error = RuntimeError("private_canary")
        error.sqlstate = "55P03"
        raise DBAPIError("private_sql", {}, error)
    s.flush = failed_flush
    with pytest.raises(CreditLifecycleError, match="^credit_busy$"):
        ensure(s)
    assert set(s.rows) == {User}
