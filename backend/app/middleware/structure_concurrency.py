from __future__ import annotations

import anyio
from starlette.types import ASGIApp, Receive, Scope, Send


class StructureConcurrencyMiddleware:
    def __init__(self, app: ASGIApp, *, max_reads: int = 2, max_streams: int = 2) -> None:
        self.app = app
        self.read_slots = anyio.Semaphore(max_reads)
        self.stream_slots = anyio.Semaphore(max_streams)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (
            path.startswith("/api/structures/") or path == "/api/queue/vasp-stats"
        ):
            await self.app(scope, receive, send)
            return

        # Slow streams must not occupy the foreground read slots.
        slots = self.stream_slots if path.endswith("/frames.stream") else self.read_slots
        async with slots:
            await self.app(scope, receive, send)
