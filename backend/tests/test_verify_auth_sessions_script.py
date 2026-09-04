import importlib.util
from pathlib import Path

import pytest


def verifier():
    path = Path(__file__).parents[2] / 'scripts/verify_auth_sessions.py'
    assert path.is_file(), 'G3 isolated auth verifier missing'
    spec = importlib.util.spec_from_file_location('verify_auth_sessions', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', ['default', 'creativeops', 'auth-verify-short', 'auth-verify-../../', 'AUTH-VERIFY-12345678'])
def test_refuses_unsafe_project(name):
    with pytest.raises(ValueError):
        verifier().validate_project(name)


def test_project_and_receipt_contract():
    m = verifier()
    assert m.validate_project('auth-verify-12345678') == 'auth-verify-12345678'
    assert not {'email', 'token', 'cookie', 'digest', 'output', 'url'} & m.RECEIPT_FIELDS
    import inspect
    assert "0006_credit_accounting_persistence" in inspect.getsource(m.verify)


@pytest.mark.parametrize('value', ['0.0.0.0:5432', '[::]:5432', 'localhost:5432', 'not-a-port'])
def test_port_must_bind_loopback(value):
    m = verifier()
    with pytest.raises(m.VerificationError):
        m.port(value)


def test_refuses_env_and_collision_before_compose(monkeypatch):
    m = verifier()
    with pytest.raises(m.VerificationError, match='only_env_example_allowed'):
        m.verify(m.ROOT / '.env')
    monkeypatch.setattr(m, 'resources', lambda project: True)
    with pytest.raises(m.VerificationError, match='project_collision'):
        m.verify(m.ROOT / '.env.example')


def test_command_error_and_timeout_are_redacted(monkeypatch):
    import subprocess
    from types import SimpleNamespace
    m = verifier()
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout='secret-sentinel', stderr='secret-sentinel'))
    with pytest.raises(m.VerificationError) as error:
        m.run(['test'])
    assert str(error.value) == 'command_failed'
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('secret-sentinel', 1)
    monkeypatch.setattr(m.subprocess, 'run', timeout)
    with pytest.raises(m.VerificationError, match='command_timeout_or_unavailable'):
        m.run(['test'])


def test_exact_cleanup_and_receipt_allowlists():
    import inspect
    m = verifier()
    source = inspect.getsource(m.verify)
    assert "'-p', project" in source
    assert "finally:" in source and "['down', '--volumes', '--remove-orphans']" in source
    assert 'set(receipt) != RECEIPT_FIELDS' in source
    assert 'METRIC_FIELDS' in source
    assert source.count("port(run(compose + ['port', 'redis', '6379']") == 2


def test_first_failure_survives_cleanup_failure(monkeypatch):
    m = verifier()
    monkeypatch.setattr(m, 'resources', lambda project: False)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[:2] == ['git', 'rev-parse']:
            return 'test-checkpoint'
        if 'down' in args:
            raise m.VerificationError('cleanup_failed')
        raise m.VerificationError('original_failure')
    monkeypatch.setattr(m, 'run', run)
    with pytest.raises(m.VerificationError, match='^original_failure; cleanup_failed$'):
        m.verify(m.ROOT / '.env.example')
    assert any('down' in args for args in calls)
