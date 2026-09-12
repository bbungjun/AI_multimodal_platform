import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_acceptance_support import HarnessError
from verify_mock_oauth_browser import MockOAuthRuntime, main, parse_message, validate_results


def rows():
    return [{"cycle": cycle, "groups": 6, "checks": 10, "external_requests": 0,
             "cleanup": 0, "seconds": 1.0} for cycle in (1, 2)]


def test_protocol_is_count_only_and_closed():
    value = '{"type":"complete","groups":6,"checks":10,"external_requests":0}'
    assert parse_message(value)["groups"] == 6
    with pytest.raises(HarnessError, match="mock_oauth_protocol_invalid"):
        parse_message('{"type":"complete","groups":6,"checks":10,"external_requests":0,"secret":"x"}')
    with pytest.raises(HarnessError, match="mock_oauth_browser_failed_login_start"):
        parse_message('{"type":"failed","phase":"login_start","code":"mock_oauth_browser_failed"}')


def test_override_is_test_only_and_uses_no_google_credentials():
    runtime = MockOAuthRuntime(ROOT / ".env.example")
    text = runtime.override_text()
    assert "mock_oauth_app:app" in text
    assert 'APP_ENV: "test"' in text
    assert 'AUTH_FRONTEND_ORIGIN: "http://127.0.0.1:18156"' in text
    assert 'AUTH_COOKIE_SECURE: "false"' in text
    assert 'AUTH_GOOGLE_CLIENT_ID: ""' in text
    assert 'AUTH_GOOGLE_CLIENT_SECRET: ""' in text
    assert 'AUTH_GOOGLE_REDIRECT_URI: ""' in text


def test_result_contract_requires_two_clean_cycles():
    assert validate_results(rows()) == {"complete": True, "cycles": 2, "groups": 6,
                                        "checks": 20, "cleanup": 0, "external_requests": 0}
    with pytest.raises(HarnessError, match="mock_oauth_acceptance_incomplete"):
        validate_results(rows()[:1])


def test_cli_refuses_arguments(capsys):
    assert main(["--cycles", "1"]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "arguments_refused"
