from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from app.synthetic_seed import SeedError, fixture_jobs, fixture_users, instant

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def test_exact_deterministic_population():
    users = fixture_users(NOW)
    assert users == fixture_users(NOW) and len({u.id for u in users}) == 120
    assert Counter(u.plan for u in users) == dict(free=84, pro=30, max=6)
    assert Counter(u.cohort for u in users) == dict(active=96, dormant=12, suspended=12)
    jobs = [j for u in users for j in fixture_jobs(u, NOW)]
    assert len(jobs) == len({j.id for j in jobs}) == 3000
    assert len({j.model for j in jobs}) == 5
    assert Counter(j.outcome for j in jobs) == dict(completed=2400, failed=360, cancelled=240)


def test_history_bounded_and_dormancy_is_activity_not_status():
    for user in fixture_users(NOW):
        jobs = fixture_jobs(user, NOW)
        assert all(user.signed_up_at <= j.created_at < NOW for j in jobs)
        assert all(j.created_at >= NOW-timedelta(days=90) for j in jobs)
        if user.cohort == "dormant":
            assert jobs[-1].created_at < NOW-timedelta(days=30)
        else:
            assert jobs[-1].created_at > NOW-timedelta(days=2)


@pytest.mark.parametrize("value", [None, "2025", datetime(2025, 1, 1), datetime(2100, 1, 1, tzinfo=timezone.utc)])
def test_invalid_asof(value):
    with pytest.raises(SeedError):
        instant(value)
