from __future__ import annotations

import asyncio
import importlib
import inspect
from collections.abc import Callable

import pytest

from app.config import Settings


def _load_worker_module():
    return importlib.import_module("app.worker")


def _settings(*, data_dir) -> Settings:
    return Settings(_env_file=None, ai_provider="mock", data_dir=data_dir)


class FakeTask:
    def __init__(self) -> None:
        self.cancel_calls = 0

    def cancel(self) -> None:
        self.cancel_calls += 1

    def done(self) -> bool:
        return False


class FakeLoop:
    def __init__(self) -> None:
        self.handlers: list[tuple[object, Callable[..., None], tuple[object, ...]]] = []
        self.removed_handlers: list[object] = []

    def add_signal_handler(
        self,
        sig: object,
        callback: Callable[..., None],
        *args: object,
    ) -> None:
        self.handlers.append((sig, callback, args))

    def remove_signal_handler(self, sig: object) -> bool:
        self.removed_handlers.append(sig)
        return True


class UnsupportedSignalLoop:
    def add_signal_handler(
        self,
        sig: object,
        callback: Callable[..., None],
        *args: object,
    ) -> None:
        raise NotImplementedError


async def test_worker_bootstrap_initializes_data_dir_schema_runner_and_db_close(
    monkeypatch,
    tmp_path,
):
    worker = _load_worker_module()
    calls: list[str] = []
    data_dir = tmp_path / "assets"

    async def fake_init_db_schema() -> None:
        calls.append("init_db_schema")

    async def fake_close_db_connection() -> None:
        calls.append("close_db_connection")

    class FakeRunner:
        def __init__(self) -> None:
            calls.append("runner.construct")

        async def run_forever(self) -> None:
            calls.append("runner.run_forever")

    monkeypatch.setattr(worker, "get_settings", lambda: _settings(data_dir=data_dir))
    monkeypatch.setattr(worker, "init_db_schema", fake_init_db_schema)
    monkeypatch.setattr(worker, "close_db_connection", fake_close_db_connection)
    monkeypatch.setattr(worker, "InProcessJobRunner", FakeRunner)

    await worker.run_worker()

    assert data_dir.exists()
    assert calls == [
        "init_db_schema",
        "runner.construct",
        "runner.run_forever",
        "close_db_connection",
    ]


async def test_worker_bootstrap_closes_db_after_runner_cancel(monkeypatch, tmp_path):
    worker = _load_worker_module()
    calls: list[str] = []
    data_dir = tmp_path / "assets"

    async def fake_init_db_schema() -> None:
        calls.append("init_db_schema")

    async def fake_close_db_connection() -> None:
        calls.append("close_db_connection")

    class CancellingRunner:
        async def run_forever(self) -> None:
            calls.append("runner.run_forever")
            raise asyncio.CancelledError

    monkeypatch.setattr(worker, "get_settings", lambda: _settings(data_dir=data_dir))
    monkeypatch.setattr(worker, "init_db_schema", fake_init_db_schema)
    monkeypatch.setattr(worker, "close_db_connection", fake_close_db_connection)
    monkeypatch.setattr(worker, "InProcessJobRunner", CancellingRunner)

    with pytest.raises(asyncio.CancelledError):
        await worker.run_worker()

    assert data_dir.exists()
    assert calls == [
        "init_db_schema",
        "runner.run_forever",
        "close_db_connection",
    ]


def test_worker_main_uses_asyncio_run(monkeypatch):
    worker = _load_worker_module()
    calls: list[str] = []

    def fake_asyncio_run(coro):
        assert inspect.iscoroutine(coro)
        calls.append(coro.cr_code.co_name)
        coro.close()

    monkeypatch.setattr(worker.asyncio, "run", fake_asyncio_run)

    worker.main()

    assert calls == ["_run_worker_until_shutdown"]


def test_worker_signal_handler_callback_cancels_task_and_cleanup_removes_handlers():
    worker = _load_worker_module()
    loop = FakeLoop()
    task = FakeTask()

    cleanup = worker._install_worker_signal_handlers(loop, task)

    registered_handlers = {
        sig: (callback, args) for sig, callback, args in loop.handlers
    }
    assert set(registered_handlers) == {
        worker.signal.SIGTERM,
        worker.signal.SIGINT,
    }

    callback, args = registered_handlers[worker.signal.SIGTERM]
    callback(*args)

    assert task.cancel_calls == 1

    cleanup()

    assert loop.removed_handlers == [
        worker.signal.SIGTERM,
        worker.signal.SIGINT,
    ]


def test_worker_signal_handler_fallback_restores_previous_handlers(monkeypatch):
    worker = _load_worker_module()
    previous_handlers = {
        worker.signal.SIGTERM: object(),
        worker.signal.SIGINT: object(),
    }
    signal_calls: list[tuple[object, object]] = []

    def fake_getsignal(sig: object) -> object:
        return previous_handlers[sig]

    def fake_signal(sig: object, handler: object) -> object:
        signal_calls.append((sig, handler))
        return previous_handlers[sig]

    monkeypatch.setattr(worker.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(worker.signal, "signal", fake_signal)

    task = FakeTask()
    cleanup = worker._install_worker_signal_handlers(UnsupportedSignalLoop(), task)

    installed_calls = signal_calls[:2]
    assert [sig for sig, _handler in installed_calls] == [
        worker.signal.SIGTERM,
        worker.signal.SIGINT,
    ]

    sigterm_handler = installed_calls[0][1]
    assert callable(sigterm_handler)
    sigterm_handler(worker.signal.SIGTERM, None)

    assert task.cancel_calls == 1

    cleanup()

    assert signal_calls[2:] == [
        (worker.signal.SIGTERM, previous_handlers[worker.signal.SIGTERM]),
        (worker.signal.SIGINT, previous_handlers[worker.signal.SIGINT]),
    ]
