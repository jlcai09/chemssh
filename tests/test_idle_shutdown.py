from __future__ import annotations

import asyncio

from backend.app.middleware.idle_shutdown import IdleShutdownManager


def test_idle_shutdown_manager_requests_callback_after_timeout() -> None:
    async def run() -> None:
        called = asyncio.Event()
        manager = IdleShutdownManager(
            timeout_seconds=0.01,
            shutdown_callback=called.set,
            check_interval_seconds=0.001,
        )

        await manager.start()
        try:
            await asyncio.wait_for(called.wait(), timeout=1)
        finally:
            await manager.stop()

    asyncio.run(run())


def test_idle_shutdown_manager_waits_for_active_request() -> None:
    async def run() -> None:
        called = asyncio.Event()
        manager = IdleShutdownManager(
            timeout_seconds=0.01,
            shutdown_callback=called.set,
            check_interval_seconds=0.001,
        )

        await manager.start()
        try:
            await manager.request_started()
            await asyncio.sleep(0.03)
            assert not called.is_set()

            await manager.request_finished()
            await asyncio.wait_for(called.wait(), timeout=1)
        finally:
            await manager.stop()

    asyncio.run(run())
