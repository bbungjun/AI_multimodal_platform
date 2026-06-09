from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Mapping
from contextlib import suppress
from typing import Any, Callable

from app.config import Settings, get_settings
from app.db import close_db_connection, init_db_schema
from app.services.jobs.runner import InProcessJobRunner


logger = logging.getLogger(__name__)
_SHUTDOWN_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class WorkerEnvironmentError(RuntimeError):
    pass


def validate_worker_environment(
    settings: Settings,
    environ: Mapping[str, str] = os.environ,
) -> None:
    provider = settings.ai_provider
    if provider == "mock":
        return

    if provider == "vertex" and environ.get("AI_PROVIDER") == "vertex":
        return

    if provider == "vertex":
        raise WorkerEnvironmentError(
            "Worker requires process env AI_PROVIDER=vertex before running "
            "with the vertex provider."
        )

    raise WorkerEnvironmentError(
        f"Worker does not support AI_PROVIDER={settings.ai_provider!r}."
    )


def _cancel_worker_task(worker_task: asyncio.Task[None], sig: signal.Signals) -> None:
    if worker_task.done():
        return
    logger.info("Worker shutdown requested by %s.", sig.name)
    worker_task.cancel()


def _install_worker_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    worker_task: asyncio.Task[None],
) -> Callable[[], None]:
    loop_handlers: list[signal.Signals] = []
    fallback_handlers: list[tuple[signal.Signals, Any]] = []
    cleaned_up = False

    for sig in _SHUTDOWN_SIGNALS:
        try:
            loop.add_signal_handler(sig, _cancel_worker_task, worker_task, sig)
        except (NotImplementedError, RuntimeError):
            try:
                previous_handler = signal.getsignal(sig)
                signal.signal(
                    sig,
                    lambda _signum, _frame, shutdown_signal=sig: _cancel_worker_task(
                        worker_task,
                        shutdown_signal,
                    ),
                )
            except (OSError, RuntimeError, ValueError):
                logger.debug("Signal handler unavailable for %s.", sig.name)
            else:
                fallback_handlers.append((sig, previous_handler))
        else:
            loop_handlers.append(sig)

    def cleanup() -> None:
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True

        for sig in loop_handlers:
            with suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(sig)

        for sig, previous_handler in fallback_handlers:
            with suppress(OSError, RuntimeError, ValueError):
                signal.signal(sig, previous_handler)

    return cleanup


async def run_worker() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    validate_worker_environment(settings)
    try:
        await init_db_schema()
        await InProcessJobRunner().run_forever()
    finally:
        await close_db_connection()


async def _run_worker_until_shutdown() -> None:
    loop = asyncio.get_running_loop()
    worker_task = asyncio.create_task(run_worker(), name="worker.run_worker")
    cleanup_signal_handlers = _install_worker_signal_handlers(loop, worker_task)
    try:
        await worker_task
    except asyncio.CancelledError:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task
        logger.info("Worker shutdown complete.")
    finally:
        cleanup_signal_handlers()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(_run_worker_until_shutdown())
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Worker shutdown requested.")


if __name__ == "__main__":
    main()
