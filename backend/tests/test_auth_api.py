import importlib
import logging
from pathlib import Path


def api_module():
    assert (Path(__file__).parents[1] / 'app/api/auth.py').is_file(), 'G3 auth HTTP module missing'
    return importlib.import_module('app.api.auth')


def test_routes_and_cookie_contract():
    m = api_module()
    assert {route.path for route in m.router.routes} == {
        '/api/auth/google/start', '/api/auth/google/callback', '/api/auth/me', '/api/auth/logout'}
    assert m.SESSION_COOKIE == 'creativeops_session'
    assert m.FLOW_COOKIE == 'creativeops_oauth_flow'


def test_callback_access_log_is_sanitized():
    assert (Path(__file__).parents[1] / 'app/auth/google.py').is_file(), 'G3 access-log sanitizer missing'
    m = importlib.import_module('app.auth.google')
    record = logging.LogRecord('uvicorn.access', 20, '', 0, '%s %s %s %s %s',
                              ('client', 'GET', '/api/auth/google/callback?code=sentinel&state=sentinel', '1.1', 303), None)
    assert m.CallbackLogFilter().filter(record)
    assert 'sentinel' not in record.getMessage()
