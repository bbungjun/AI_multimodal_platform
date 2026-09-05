from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.master_read import MasterReadError, amount, project_user, safe_values

T = datetime(2025, 1, 1, tzinfo=timezone.utc)


def row(**changes):
    return dict(id=UUID(int=1), role="user", status="active", data_origin="synthetic",
        signed_up_at=T, account_plan=None, pending_plan=None, cycle_anchor_at=None,
        cycle_index=None, cycle_id=None) | changes


def test_uninitialized_projection_has_exact_boundary_and_no_model_guess():
    result = project_user(row(), [], 0, 0, T+timedelta(days=30))
    assert result["cycle_starts_at"] == T+timedelta(days=30)
    assert result["renews_at"] == T+timedelta(days=60)
    assert result["available_microcredits"] == "1000000000"
    assert not result["balance_materialized"] and result["plan"] == "free"


def test_pending_projection_retains_old_hold_and_excludes_old_base():
    source = row(account_plan="pro", pending_plan="free", cycle_anchor_at=T, cycle_index=0, cycle_id=UUID(int=4))
    grant = dict(kind="base", cycle_id=UUID(int=4), expires_at=T+timedelta(days=30),
        granted_microcredits=10_000_000_000, reserved_microcredits=20, consumed_microcredits=30, expired_microcredits=0)
    result = project_user(source, [grant], 20, 10, T+timedelta(days=30))
    assert result["available_microcredits"] == "1000000000"
    assert result["held_microcredits"] == "20" and result["charged_microcredits"] == "10"
    assert result["plan"] == "free" and result["pending_plan"] is None


@pytest.mark.parametrize("value", [True, -1, 1.1, "1", Decimal("1.2"), Decimal("NaN")])
def test_money_rejects_lossy_or_negative(value):
    with pytest.raises(MasterReadError):
        amount(value)


def test_money_preserves_aggregate_precision():
    assert amount(Decimal(2**80)) == str(2**80)


@pytest.mark.parametrize("value", [{"email": "forbidden"}, {"role": {}}, {"status": "secret"},
    {"bonus_microcredits": True}, {"plan": ["free"]}, {"cancelled_jobs": -1}, {"revoked_sessions": 2**60}])
def test_audit_values_fail_closed(value):
    with pytest.raises(MasterReadError):
        safe_values(value)


def test_safe_audit_integer_contract():
    assert safe_values(dict(role="user", status="active", plan=None, pending_plan=None,
        bonus_microcredits=2**60, revoked_sessions=2)) == dict(role="user", status="active",
        plan=None, pending_plan=None, bonus_microcredits=str(2**60), revoked_sessions=2)


@pytest.mark.parametrize("changes,held", [({"account_plan": "free"}, 0), ({}, 1),
    ({"account_plan": "free", "cycle_index": 9, "cycle_anchor_at": T}, 0)])
def test_corrupt_projection_refused(changes, held):
    with pytest.raises(MasterReadError):
        project_user(row(**changes), [], held, 0, T)
