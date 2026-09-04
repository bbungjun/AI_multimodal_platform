import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        'verify_emergency_sessions', ROOT / 'scripts/verify_emergency_sessions.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(module):
    return {
        'groups': dict.fromkeys(module.GROUPS, True),
        'races': 1,
        'checks': 80,
        'complete': True,
    }


def test_receipt_contract_budgets_and_activation():
    module = load()
    value = payload(module)
    assert module.parse_proof(json.dumps(value)) == value
    module.activate()
    assert module.base.HEAD == '0006_credit_accounting_persistence'
    assert module.base.WORK_SECONDS == 120
    assert module.base.CLEANUP_SECONDS == 60


@pytest.mark.parametrize('change', [
    {'complete': False}, {'races': 0}, {'races': True}, {'checks': 79},
    {'checks': True}, {'groups': {}}, {'extra': 'fixed'},
])
def test_bad_receipt_refused(change):
    module = load()
    value = payload(module)
    value.update(change)
    with pytest.raises(module.Failure, match='receipt_invalid'):
        module.parse_proof(json.dumps(value))


@pytest.mark.parametrize('value', [
    'default', 'emergency-auth-verify-123',
    'emergency-auth-verify-123456ABCDEF', 'emergency-auth-verify-../',
])
def test_project_guard(value):
    module = load()
    with pytest.raises(module.Failure, match='target_refused'):
        module.validate_project(value)


def test_private_env_refused_without_read(tmp_path):
    module = load()
    with pytest.raises(module.Failure, match='env_file_refused'):
        module.Runtime(tmp_path / '.env')


def test_config_forces_isolated_target_and_disabled_login(tmp_path, monkeypatch):
    module = load()
    module.activate()
    monkeypatch.delenv('DOCKER_HOST', raising=False)
    config = {
        'services': {
            'db': {'image': 'postgres:16', 'ports': ['5432'], 'healthcheck': {'test': []}},
            'migrate': {'build': {'context': 'fixed'}},
            'backend': {},
        }
    }
    runtime = module.Runtime(
        ROOT / '.env.example', run=lambda *args, **kwargs: json.dumps(config)
    )
    runtime.configure(tmp_path)
    selected = json.loads((tmp_path / 'compose.json').read_text(encoding='utf-8'))
    assert set(selected['services']) == {'db', 'migrate'}
    environment = selected['services']['migrate']['environment']
    assert environment['EMERGENCY_SESSION_PROOF_PROJECT'] == runtime.project
    assert environment['AUTH_LOGIN_ENABLED'] == 'false'
    assert 'ACCOUNTING_PROOF_PROJECT' not in environment
    assert selected['volumes']['pgdata']['labels'][module.base.LABEL] == runtime.nonce


def test_cli_has_no_target_or_cleanup_bypass():
    module = load()
    for flag in ('--project-name', '--dsn', '--source', '--keep-volumes', '--evidence-dir'):
        with pytest.raises(SystemExit):
            module.main([flag, 'fixture'])
