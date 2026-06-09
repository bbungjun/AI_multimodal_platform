from __future__ import annotations

import asyncio
import importlib

import pytest

from app.config import Settings, get_settings


def _load_main_module(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    import app.main as main

    return importlib.reload(main)


def _settings(*, data_dir, job_runner_auto_start: bool) -> Settings:
    return Settings(
        _env_file=None,
        ai_provider="mock",
        data_dir=data_dir,
        job_runner_auto_start=job_runner_auto_start,
    )


async def test_lifespan_skips_runner_when_auto_start_disabled(monkeypatch, tmp_path):
    main = _load_main_module(monkeypatch, tmp_path)
    calls: list[str] = []
    data_dir = tmp_path / "assets"

    async def fake_init_db_schema() -> None:
        calls.append("init_db_schema")

    async def fake_close_db_connection() -> None:
        calls.append("close_db_connection")

    async def fake_job_runner() -> None:
        calls.append("job_runner")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            calls.append("job_runner_cancelled")
            raise

    monkeypatch.setattr(main, "settings", _settings(data_dir=data_dir, job_runner_auto_start=False))
    monkeypatch.setattr(main, "init_db_schema", fake_init_db_schema)
    monkeypatch.setattr(main, "close_db_connection", fake_close_db_connection)
    monkeypatch.setattr(main, "job_runner", fake_job_runner)

    async with main.lifespan(object()):
        calls.append("yield")
        await asyncio.sleep(0)

    assert data_dir.exists()
    assert calls == ["init_db_schema", "yield", "close_db_connection"]


async def test_lifespan_starts_runner_when_auto_start_enabled(monkeypatch, tmp_path):
    main = _load_main_module(monkeypatch, tmp_path)
    calls: list[str] = []
    data_dir = tmp_path / "assets"

    async def fake_init_db_schema() -> None:
        calls.append("init_db_schema")

    async def fake_close_db_connection() -> None:
        assert calls.count("job_runner_started") == 1
        assert "job_runner_cancelled" in calls
        calls.append("close_db_connection")

    async def fake_job_runner() -> None:
        calls.append("job_runner_started")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            calls.append("job_runner_cancelled")
            raise

    monkeypatch.setattr(main, "settings", _settings(data_dir=data_dir, job_runner_auto_start=True))
    monkeypatch.setattr(main, "init_db_schema", fake_init_db_schema)
    monkeypatch.setattr(main, "close_db_connection", fake_close_db_connection)
    monkeypatch.setattr(main, "job_runner", fake_job_runner)

    async with main.lifespan(object()):
        calls.append("yield")
        await asyncio.sleep(0)

    assert data_dir.exists()
    assert calls == [
        "init_db_schema",
        "yield",
        "job_runner_started",
        "job_runner_cancelled",
        "close_db_connection",
    ]


async def test_lifespan_always_closes_db_connection(monkeypatch, tmp_path):
    main = _load_main_module(monkeypatch, tmp_path)
    calls: list[str] = []
    data_dir = tmp_path / "assets"

    async def fake_init_db_schema() -> None:
        calls.append("init_db_schema")

    async def fake_close_db_connection() -> None:
        calls.append("close_db_connection")

    async def fake_job_runner() -> None:
        calls.append("job_runner")
        await asyncio.Event().wait()

    monkeypatch.setattr(main, "settings", _settings(data_dir=data_dir, job_runner_auto_start=False))
    monkeypatch.setattr(main, "init_db_schema", fake_init_db_schema)
    monkeypatch.setattr(main, "close_db_connection", fake_close_db_connection)
    monkeypatch.setattr(main, "job_runner", fake_job_runner)

    with pytest.raises(RuntimeError, match="lifespan body failed"):
        async with main.lifespan(object()):
            raise RuntimeError("lifespan body failed")

    assert calls == ["init_db_schema", "close_db_connection"]
