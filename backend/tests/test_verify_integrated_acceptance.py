"""Receipt and safe failure contracts for the integration coordinator."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("integrated", Path(__file__).parents[2] / "scripts/verify_integrated_acceptance.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def valid_rows():
    return [dict(passed=True, cleanup=True, code_revision="a" * 40, cycle=i,
                 suite="custom", scenarios=8, admission_checks=80) for i in (1, 2)]


def test_receipt_is_bounded_and_not_live():
    receipt = module.validate_results(valid_rows(), "a" * 40)
    assert receipt["live_verified"] is False
    assert receipt["cleanup_remaining"] == 0
    assert receipt["groups"] == list(module.GROUPS)
    assert set(receipt) == {"provider", "code_revision", "cycles", "groups", "checks",
                            "cleanup_remaining", "passed", "live_verified"}


@pytest.mark.parametrize("field,value", [("passed", False), ("cleanup", False),
    ("code_revision", "b" * 40), ("cycle", 3), ("suite", "ownership"),
    ("scenarios", 7), ("admission_checks", 39), ("admission_checks", True)])
def test_incomplete_receipt_refused(field, value):
    rows = valid_rows()
    rows[0][field] = value
    with pytest.raises(module.HarnessError):
        module.validate_results(rows, "a" * 40)


@pytest.mark.parametrize("rows", [None, [], [{}]])
def test_two_cycles_required(rows):
    with pytest.raises(module.HarnessError):
        module.validate_results(rows, "a" * 40)


def test_failure_does_not_emit_raw_exception(capsys):
    def fail(*args):
        raise ValueError("private-session-prompt-example")
    with pytest.raises(module.HarnessError, match="integration_failed"):
        module.scenarios(SimpleNamespace(base_url="http://127.0.0.1:1234"), SimpleNamespace(client=fail))
    assert capsys.readouterr().out == '{"integration_failed_group": "identity"}\n'


def test_existing_owned_guards_are_reused():
    source = Path(module.__file__).read_text()
    assert 'verify_cycles(ROOT / ".env.example", 2, scenario=scenarios)' in source
    assert 'runtime.assert_owned()' in source
    assert 'runtime.docker(*runtime.compose, "stop", "dispatcher", "worker")' in source
    assert 'database_url' not in source.lower()


@pytest.mark.parametrize("path,cache,safe", [
    ("/api/auth/me", "no-store", True), ("/api/auth/me", "private", False),
    ("/api/usage/me", "no-store", False), ("/api/master/audit", "private, no-store", True),
    ("/api/generations", "private, no-store", True)])
def test_cache_contract_distinguishes_auth_from_content(path, cache, safe):
    assert module.cache_is_safe(path, cache) is safe
