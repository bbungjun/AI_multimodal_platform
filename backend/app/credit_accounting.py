"""Atomic credit accounting behind a small caller-owned transaction Interface."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import UUID

from sqlalchemy.exc import DBAPIError


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
    raise CreditAccountingError("credit_account_inconsistent")


async def _terminal(session, user_id, reservation_id, lines, delivery, reason, key, now, charge):
    raise CreditAccountingError("credit_account_inconsistent")
