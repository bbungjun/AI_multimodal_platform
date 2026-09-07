"""Refuse unsafe fixtures and false successful drains before running real load."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from verify_user_journey_load import drained, PROFILES
from user_journey_fixtures import validate


def payload():
    return {"project": "ownership-verify-123456abcdef", "operation": "snapshot", "hashes": []}


@pytest.mark.parametrize("host,database,provider,app_env", [
    ("remote", "ownership_verify_123456abcdef", "mock", "local"),
    ("db", "developer", "mock", "local"),
    ("db", "ownership_verify_123456abcdef", "vertex", "local"),
    ("db", "ownership_verify_123456abcdef", "mock", "production"),
])
def test_fixture_refuses_nonowned_or_live_targets(host, database, provider, app_env):
    with pytest.raises(ValueError, match="load_target_refused"):
        validate(payload(), host, database, provider, app_env)


def test_seed_requires_distinct_hashes_and_read_modes_reject_secrets():
    request = payload()
    request.update(operation="seed", hashes=["a" * 64] * 64)
    with pytest.raises(ValueError, match="load_hashes_refused"):
        validate(request, "db", "ownership_verify_123456abcdef", "mock", "local")
    request.update(operation="snapshot", hashes=["a" * 64])
    with pytest.raises(ValueError, match="load_hashes_refused"):
        validate(request, "db", "ownership_verify_123456abcdef", "mock", "local")


@pytest.mark.parametrize("key,value", [
    ("jobs", {"pending": 1}), ("jobs", {"queued": 1}),
    ("outbox", {"pending": 1}), ("outbox", {"failed": 1}),
    ("reservations", {"held": 1}), ("held_microcredits", 1),
])
def test_drain_rejects_stranded_work_or_accounting(key, value):
    snapshot = {"jobs": {"completed": 5}, "outbox": {"published": 5},
                "reservations": {"settled": 5}, "held_microcredits": 0}
    assert drained(snapshot)
    snapshot[key] = value
    assert not drained(snapshot)


def test_load_has_explicit_arrivals_with_enough_distinct_users():
    for profile in PROFILES.values():
        assert profile["rate"] > 0 and 0 < profile["vus"] <= 64
