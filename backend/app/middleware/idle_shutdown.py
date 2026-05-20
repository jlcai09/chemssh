from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress

from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger(__name__)

ShutdownCallback = Callable[[], None | Awaitable[None]]


class IdleShutdownManager:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        shutdown_callback: ShutdownCallback | None = None,
        check_interval_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.shutdown_callback = shutdown_callback
        self.check_interval_seconds = check_interval_seconds or self._default_check_interval(timeout_seconds)
        self.clock = clock

        self._active_requests = 0
        self._last_activity_at = clock()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._shutdown_requested = False

    @property
    def enabled(self) -> bool:
        return self.timeout_seconds > 0

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return

        self._last_activity_at = self.clock()
        self._task = asyncio.create_task(self._monitor(), name="chemweb-idle-shutdown")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None or task.done():
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def request_started(self) -> None:
        if not self.enabled:
            return

        async with self._lock:
            self._active_requests += 1
            self._last_activity_at = self.clock()

    async def request_finished(self) -> None:
        if not self.enabled:
            return

        async with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._last_activity_at = self.clock()

    async def _monitor(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.check_interval_seconds)
                if await self._timed_out():
                    await self._request_shutdown()
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Idle shutdown monitor failed")

    async def _timed_out(self) -> bool:
        async with self._lock:
            if self._shutdown_requested or self._active_requests > 0:
                return False
            return self.clock() - self._last_activity_at >= self.timeout_seconds

    async def _request_shutdown(self) -> None:
        async with self._lock:
            if self._shutdown_requested:
                return
            self._shutdown_requested = True

        logger.info("No requests received for %.0f seconds; shutting down backend.", self.timeout_seconds)
        if self.shutdown_callback is None:
            logger.warning("Idle shutdown requested, but no shutdown callback is configured.")
            return

        result = self.shutdown_callback()
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _default_check_interval(timeout_seconds: float) -> float:
        if timeout_seconds <= 0:
            return 1.0
        return min(max(timeout_seconds / 10, 1.0), 30.0)


class IdleShutdownMiddleware:
    def __init__(self, app: ASGIApp, *, manager: IdleShutdownManager) -> None:
        self.app = app
        self.manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"} or not self.manager.enabled:
            await self.app(scope, receive, send)
            return

        await self.manager.request_started()
        try:
            await self.app(scope, receive, send)
        finally:
            await self.manager.request_finished()
