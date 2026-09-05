from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import pytest

from app import synthetic_seed_cli as cli
from app.synthetic_seed import SeedError, report

NAME = "master_seed_verify_123456abcdef"


def settings(**changes):
    return SimpleNamespace(**(dict(database_url="postgresql+asyncpg://db/"+NAME,
        ai_provider="mock", app_env="test") | changes))


def test_target_and_apply_confirmation():
    cli.validate_target(settings(), NAME, False, None)
    cli.validate_target(settings(), NAME, True, "SEED")


@pytest.mark.parametrize("change", [dict(app_env="production"), dict(app_env="local"), dict(ai_provider="vertex"),
    dict(database_url="postgresql://remote/"+NAME), dict(database_url="postgresql://db/developer")])
def test_nonowned_or_live_target_refused(change):
    with pytest.raises(SeedError):
        cli.validate_target(settings(**change), NAME, False, None)


@pytest.mark.parametrize("target,execute,confirm", [("developer", False, None), (NAME, True, None), (NAME, True, "yes")])
def test_guard_is_not_only_a_warning(target, execute, confirm):
    with pytest.raises(SeedError):
        cli.validate_target(settings(), target, execute, confirm)


@pytest.mark.asyncio
async def test_preview_always_rolls_back(monkeypatch):
    class Session:
        rollback = AsyncMock()
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        def begin(self): return self
    session = Session()
    monkeypatch.setattr(cli, "get_settings", settings)
    monkeypatch.setattr(cli, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(cli, "seed_fixture", AsyncMock(return_value=report(False)))
    monkeypatch.setattr(cli, "close_db_connection", AsyncMock())
    result = await cli.run(SimpleNamespace(expected_database=NAME, execute=False, confirm=None,
                                          as_of=datetime(2026, 9, 5, tzinfo=timezone.utc)))
    assert result["mode"] == "preview" and result["users"] == 120
    session.rollback.assert_awaited_once()
