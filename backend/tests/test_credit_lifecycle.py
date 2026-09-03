"""Unit fakes exercise the lifecycle Interface; PostgreSQL proof is separate."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.credit_lifecycle import CreditLifecycleError, ensure_cycle
from app.credit_models import CreditAccount, CreditCycle, CreditGrant, CreditLedgerEvent
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
