from __future__ import annotations

import argparse
import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.identity_models import UserSession


SAFE_REASONS = frozenset({
    'suspected_compromise',
    'credential_rotation',
    'operator_drill',
})
SYSTEM_DATABASES = frozenset({'postgres', 'template0', 'template1'})


class EmergencyRevocationError(Exception):
    """A bounded operational error that cannot expose database or Session data."""

    CODES = frozenset({
        'invalid_reason', 'invalid_time', 'invalid_execute',
        'transaction_required', 'unsupported_database',
        'system_database_refused', 'database_mismatch', 'login_enabled',
        'confirmation_required', 'confirmation_mismatch',
        'revocation_unavailable',
    })

    def __init__(self, code: str):
        self.code = code if code in self.CODES else 'revocation_unavailable'
        super().__init__(self.code)


@dataclass(frozen=True)
class EmergencyRevocationReceipt:
    reason: str
    execute: bool
    active_before: int
    revoked: int
    active_after: int


def format_receipt(receipt: EmergencyRevocationReceipt) -> str:
    mode = 'execute' if receipt.execute else 'preview'
    return (
        f'PASS: emergency_session_revocation mode={mode} reason={receipt.reason} '
        f'active_before={receipt.active_before} revoked={receipt.revoked} '
        f'active_after={receipt.active_after}'
    )


def validate_emergency_target(
    database_url: str,
    *,
    expected_database: str,
    login_enabled: bool,
    execute: bool,
    confirmation: str | None,
) -> str:
    try:
        url = make_url(database_url)
    except Exception:
        raise EmergencyRevocationError('unsupported_database') from None
    database = url.database
    if url.get_backend_name() != 'postgresql' or not database:
        raise EmergencyRevocationError('unsupported_database')
    if database.lower() in SYSTEM_DATABASES:
        raise EmergencyRevocationError('system_database_refused')
    if (not isinstance(expected_database, str)
            or re.fullmatch(r'[A-Za-z0-9_-]{1,63}', expected_database) is None
            or expected_database != database):
        raise EmergencyRevocationError('database_mismatch')
    if login_enabled:
        raise EmergencyRevocationError('login_enabled')
    if type(execute) is not bool:
        raise EmergencyRevocationError('invalid_execute')
    if execute:
        if confirmation is None:
            raise EmergencyRevocationError('confirmation_required')
        if confirmation != f'REVOKE_ALL:{database}':
            raise EmergencyRevocationError('confirmation_mismatch')
    return database


async def revoke_active_sessions(
    session,
    *,
    reason: str,
    now: datetime,
    execute: bool,
) -> EmergencyRevocationReceipt:
    if reason not in SAFE_REASONS:
        raise EmergencyRevocationError('invalid_reason')
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise EmergencyRevocationError('invalid_time')
    if type(execute) is not bool:
        raise EmergencyRevocationError('invalid_execute')
    if not session.in_transaction():
        raise EmergencyRevocationError('transaction_required')

    statement = (
        select(UserSession)
        .where(UserSession.revoked_at.is_(None))
        .order_by(UserSession.user_id, UserSession.created_at, UserSession.id)
    )
    if execute:
        statement = statement.with_for_update()
    try:
        rows = list((await session.execute(statement)).scalars().all())
        active_before = len(rows)
        if execute:
            bounded_reason = f'emergency_{reason}'
            for row in rows:
                row.revoked_at = max(now, row.created_at)
                row.revoke_reason = bounded_reason
            await session.flush()
        revoked = active_before if execute else 0
        return EmergencyRevocationReceipt(
            reason, execute, active_before, revoked,
            active_before - revoked,
        )
    except SQLAlchemyError:
        raise EmergencyRevocationError('revocation_unavailable') from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Guarded emergency Session revocation')
    parser.add_argument('--expected-database', required=True)
    parser.add_argument('--reason', required=True, choices=sorted(SAFE_REASONS))
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--confirm')
    return parser


async def _run_cli(args) -> EmergencyRevocationReceipt:
    from app.config import get_settings
    from app.db import AsyncSessionLocal

    settings = get_settings()
    validate_emergency_target(
        settings.database_url,
        expected_database=args.expected_database,
        login_enabled=settings.auth_login_enabled,
        execute=args.execute,
        confirmation=args.confirm,
    )
    async with AsyncSessionLocal() as session, session.begin():
        return await revoke_active_sessions(
            session,
            reason=args.reason,
            now=datetime.now(timezone.utc),
            execute=args.execute,
        )


def main() -> int:
    args = _parser().parse_args()
    try:
        receipt = asyncio.run(_run_cli(args))
    except EmergencyRevocationError as error:
        print(f'FAIL: {error.code}')
        return 2
    print(format_receipt(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
