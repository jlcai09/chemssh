from __future__ import annotations

import asyncio

import pytest

from backend.app.middleware.structure_concurrency import StructureConcurrencyMiddleware


@pytest.mark.parametrize("path", ["/api/structures/ase/frames.bin", "/api/structures/ase/frames.stream", "/api/queue/vasp-stats"])
def test_structure_slots_are_held_until_body_is_sent(path: str) -> None:
    async def run() -> None:
        started = []
        blocked_send = asyncio.Event()
        release = asyncio.Event()

        async def app(scope, receive, send):
            started.append(scope["id"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"chunk"})

        async def send(message):
            if message["type"] == "http.response.body":
                blocked_send.set()
                await release.wait()

        async def receive():
            return {"type": "http.request", "body": b""}

        middleware = StructureConcurrencyMiddleware(app, max_reads=1, max_streams=1)
        first = asyncio.create_task(middleware({"type": "http", "path": path, "id": 1}, receive, send))
        await blocked_send.wait()
        second = asyncio.create_task(middleware({"type": "http", "path": path, "id": 2}, receive, send))
        await asyncio.sleep(0)
        assert started == [1]
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), 1)
        assert started == [1, 2]

    asyncio.run(run())


def test_streams_do_not_block_foreground_or_unrelated_requests() -> None:
    async def run() -> None:
        stream_started = asyncio.Event()
        release = asyncio.Event()
        completed = []

        async def app(scope, receive, send):
            if scope["path"].endswith("frames.stream"):
                stream_started.set()
                await release.wait()
            completed.append(scope["path"])

        middleware = StructureConcurrencyMiddleware(app, max_reads=1, max_streams=1)
        stream = asyncio.create_task(middleware({"type": "http", "path": "/api/structures/ase/frames.stream"}, None, None))
        await stream_started.wait()
        for path in ("/api/structures/ase/frame", "/api/system/info", "/api/files/list"):
            await asyncio.wait_for(middleware({"type": "http", "path": path}, None, None), 1)
            assert path in completed
        release.set()
        await stream

    asyncio.run(run())


@pytest.mark.parametrize("cancel_waiter", [True, False])
def test_cancelled_and_failed_requests_release_slots(cancel_waiter: bool) -> None:
    async def run() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def app(scope, receive, send):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()
                raise RuntimeError("injected failure")

        middleware = StructureConcurrencyMiddleware(app, max_reads=1)
        scope = {"type": "http", "path": "/api/structures/ase/frame"}
        first = asyncio.create_task(middleware(scope, None, None))
        await started.wait()
        second = asyncio.create_task(middleware(scope, None, None))
        await asyncio.sleep(0)
        cancelled = second if cancel_waiter else first
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        if cancel_waiter:
            release.set()
            with pytest.raises(RuntimeError, match="injected failure"):
                await first
        else:
            await asyncio.wait_for(second, 1)
        await asyncio.wait_for(middleware(scope, None, None), 1)

    asyncio.run(run())
