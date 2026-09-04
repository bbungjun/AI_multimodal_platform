"""Tests cross only the public accounting Interface; PostgreSQL proof is separate."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import UUID

import pytest

import app.credit_accounting as accounting

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
