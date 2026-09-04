import importlib
import inspect
from datetime import datetime, timezone

import pytest


def emergency_module():
    return importlib.import_module('app.auth.emergency')


def test_deep_module_interface_and_bounded_receipt():
    m = emergency_module()
    signature = inspect.signature(m.revoke_active_sessions)
    assert tuple(signature.parameters) == ('session', 'reason', 'now', 'execute')
    assert signature.parameters['reason'].kind is inspect.Parameter.KEYWORD_ONLY
    assert m.SAFE_REASONS == frozenset({
        'suspected_compromise', 'credential_rotation', 'operator_drill'})
    receipt = m.EmergencyRevocationReceipt('operator_drill', False, 3, 0, 3)
    assert m.format_receipt(receipt) == (
        'PASS: emergency_session_revocation mode=preview reason=operator_drill '
        'active_before=3 revoked=0 active_after=3')
    assert 'id=' not in repr(receipt).lower()


@pytest.mark.parametrize('reason', ['', 'other', 'operator-drill', 'x' * 65])
async def test_module_rejects_unsafe_reason_before_database_work(reason):
    m = emergency_module()

    class Session:
        def in_transaction(self):
            return True

        async def execute(self, *args):
            raise AssertionError('invalid reason must fail before SQL')

    with pytest.raises(m.EmergencyRevocationError, match='^invalid_reason$'):
        await m.revoke_active_sessions(
            Session(), reason=reason, now=datetime.now(timezone.utc), execute=False)


async def test_module_requires_aware_time_active_transaction_and_bool_execute():
    m = emergency_module()

    class Session:
        def __init__(self, active):
            self.active = active

        def in_transaction(self):
            return self.active

    cases = [
        (Session(True), datetime(2026, 1, 1), False, 'invalid_time'),
        (Session(False), datetime.now(timezone.utc), False, 'transaction_required'),
        (Session(True), datetime.now(timezone.utc), 1, 'invalid_execute'),
    ]
    for session, now, execute, code in cases:
        with pytest.raises(m.EmergencyRevocationError, match=f'^{code}$'):
            await m.revoke_active_sessions(
                session, reason='operator_drill', now=now, execute=execute)


@pytest.mark.parametrize(
    'url,expected,enabled,execute,confirm,code',
    [
        ('sqlite:///fixture', 'fixture', False, False, None, 'unsupported_database'),
        ('postgresql+asyncpg://app@db:5432/postgres', 'postgres', False, False, None,
         'system_database_refused'),
        ('postgresql+asyncpg://app@db:5432/isolated', 'other', False, False, None,
         'database_mismatch'),
        ('postgresql+asyncpg://app@db:5432/isolated', 'isolated', True, False, None,
         'login_enabled'),
        ('postgresql+asyncpg://app@db:5432/isolated', 'isolated', False, True, None,
         'confirmation_required'),
        ('postgresql+asyncpg://app@db:5432/isolated', 'isolated', False, True,
         'REVOKE_ALL:other', 'confirmation_mismatch'),
    ],
)
def test_cli_target_and_confirmation_guards(url, expected, enabled, execute, confirm, code):
    m = emergency_module()
    with pytest.raises(m.EmergencyRevocationError, match=f'^{code}$'):
        m.validate_emergency_target(
            url, expected_database=expected, login_enabled=enabled,
            execute=execute, confirmation=confirm)


def test_cli_valid_preview_and_execute_return_only_database_name():
    m = emergency_module()
    url = 'postgresql+asyncpg://app:secret@db:5432/isolated'
    assert m.validate_emergency_target(
        url, expected_database='isolated', login_enabled=False,
        execute=False, confirmation=None) == 'isolated'
    assert m.validate_emergency_target(
        url, expected_database='isolated', login_enabled=False,
        execute=True, confirmation='REVOKE_ALL:isolated') == 'isolated'
