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
