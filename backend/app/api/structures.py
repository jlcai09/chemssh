from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar

import anyio
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse

from backend.app.core.errors import AppError
from backend.app.dependencies import get_structure_service
from backend.app.models.structure import (
    AseDynamicDisplayRequest,
    AseDynamicDisplayResponse,
    AseFragmentRequest,
    AseFragmentResponse,
    AseFrame,
    AseFrameChunkResponse,
    AsePreviewResponse,
)
from backend.app.services.structure_types import STRUCTURE_BINARY_MEDIA_TYPE, StructureCancellationToken

if TYPE_CHECKING:
    from backend.app.services.structure_service import StructureService
else:
    # The concrete service imports ase/scipy/numpy; keep it out of module import so
    # server startup does not pay that cost. FastAPI only needs a resolvable hint.
    StructureService = Any


router = APIRouter(prefix="/structures", tags=["structures"])
T = TypeVar("T")


def _structure_debug_enabled(request: Request) -> bool:
    settings = getattr(request.app.state, "settings", None)
    server = getattr(settings, "server", None)
    return bool(getattr(server, "debug", False))


async def run_with_disconnect_cancellation(
    request: Request,
    operation: Callable[[StructureCancellationToken], T],
) -> T:
    cancellation = StructureCancellationToken()
    result: T | None = None
    error: Exception | None = None

    async def watch_disconnect() -> None:
        while True:
            if await request.is_disconnected():
                cancellation.cancel()
                return
            await anyio.sleep(0.1)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(watch_disconnect)
        try:
            result = await anyio.to_thread.run_sync(lambda: operation(cancellation))
        except Exception as exc:
            error = exc
        finally:
            cancellation.cancel()
            task_group.cancel_scope.cancel()

    if error:
        raise error
    return result  # type: ignore[return-value]


@router.get("/ase/preview", response_model=AsePreviewResponse)
async def read_ase_preview(
    request: Request,
    path: str,
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    service: StructureService = Depends(get_structure_service),
) -> AsePreviewResponse:
    return await run_with_disconnect_cancellation(
        request,
        lambda cancellation: service.preview(path, format, force=force, cancellation=cancellation),
    )


@router.get("/ase/frame", response_model=AseFrame)
def read_ase_frame(
    path: str,
    index: int = Query(ge=0),
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    service: StructureService = Depends(get_structure_service),
) -> AseFrame:
    return service.read_frame(path, index, format, force=force)


@router.post("/ase/fragments", response_model=AseFragmentResponse)
async def query_ase_fragments(
    request: Request,
    payload: AseFragmentRequest,
    service: StructureService = Depends(get_structure_service),
) -> AseFragmentResponse:
    return await run_with_disconnect_cancellation(
        request,
        lambda cancellation: service.query_fragments(payload, cancellation=cancellation),
    )


@router.post("/ase/dynamic-display", response_model=AseDynamicDisplayResponse)
async def evaluate_ase_dynamic_display(
    request: Request,
    payload: AseDynamicDisplayRequest,
    service: StructureService = Depends(get_structure_service),
) -> AseDynamicDisplayResponse:
    return await run_with_disconnect_cancellation(
        request,
        lambda cancellation: service.evaluate_dynamic_display(payload, cancellation=cancellation),
    )


@router.get("/ase/frames", response_model=AseFrameChunkResponse)
def read_ase_frame_chunk_json(
    path: str,
    start: int = Query(ge=0),
    count: int = Query(gt=0),
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    service: StructureService = Depends(get_structure_service),
) -> AseFrameChunkResponse:
    return service.read_frame_chunk_json(path, start, count, format, force=force)


@router.get("/ase/frames.bin")
def read_ase_frame_chunk(
    path: str,
    start: int = Query(ge=0),
    count: int = Query(gt=0),
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    service: StructureService = Depends(get_structure_service),
) -> Response:
    return Response(
        content=service.read_frame_chunk_binary(path, start, count, format, force=force),
        media_type=STRUCTURE_BINARY_MEDIA_TYPE,
    )


@router.get("/ase/frames.stream")
async def stream_ase_frames(
    request: Request,
    path: str,
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    chunk: int = Query(default=32, ge=1, le=512),
    service: StructureService = Depends(get_structure_service),
) -> StreamingResponse:
    """SSE stream that pushes binary frame chunks continuously.

    Each SSE event carries a base64-encoded CWB1 binary payload (same format as
    ``/frames.bin``).  The client opens one EventSource connection and receives
    all chunks without further requests, eliminating N serial HTTP round-trips.

    Debug-only event types:
      - ``ready``: data is ``{"t_resolve_ms", "t_scan_ms", "total_frames", "chunk_size", "server_emit_ms"}``
      - ``meta``:  data is ``{"start", "count", "t_pack_ms", "t_b64_ms", "server_emit_ms", "size_b64", "profile"}`` (precedes every ``chunk``)

    Always-on event types:
      - ``chunk``: data is base64(CWB1 payload)
      - ``done``:  data is ``{"n_frames": <int>}``
      - ``error``: data is ``{"code": "<str>", "message": "<str>"}``
    """

    async def event_generator():
        cancellation = StructureCancellationToken()
        debug_timings = _structure_debug_enabled(request)

        # Background watcher that cancels on client disconnect.
        async def watch_disconnect() -> None:
            while True:
                if await request.is_disconnected():
                    cancellation.cancel()
                    return
                await anyio.sleep(0.1)

        watch_task = asyncio.create_task(watch_disconnect())

        try:
            # Resolve and scan before emitting chunks so the client receives total frame metadata first.
            t_resolve_0 = time.perf_counter() if debug_timings else 0.0
            try:
                resolved = await anyio.to_thread.run_sync(
                    lambda: service._resolve_structure_file(path, force=force),
                )
            except Exception as exc:
                yield _sse_event("error", json.dumps({"code": "RESOLVE_FAILED", "message": str(exc)}))
                return
            t_resolve_ms = (time.perf_counter() - t_resolve_0) * 1000.0 if debug_timings else 0.0

            t_scan_0 = time.perf_counter() if debug_timings else 0.0
            try:
                allow_incomplete = not service.stream_requires_complete_summary(resolved, format)
                summary = await anyio.to_thread.run_sync(
                    lambda: service._get_structure_summary(
                        resolved,
                        format,
                        cancellation,
                        allow_incomplete=allow_incomplete,
                    ),
                )
                if not summary.scan_completed and service.stream_requires_complete_summary(resolved, format, summary):
                    summary = await anyio.to_thread.run_sync(
                        lambda: service._get_structure_summary(resolved, format, cancellation, allow_incomplete=False),
                    )
            except Exception as exc:
                yield _sse_event("error", json.dumps({"code": "SCAN_FAILED", "message": str(exc)}))
                return
            t_scan_ms = (time.perf_counter() - t_scan_0) * 1000.0 if debug_timings else 0.0

            n_frames = summary.n_frames
            chunk_size = service.frame_chunk_count(summary, chunk)

            # Initial metadata: backend timing + frame count. Client pairs
            # server_emit_ms with EPOCH_OFFSET_AT_LOAD to compute drift.
            if debug_timings:
                yield _sse_event("ready", json.dumps({
                    "t_resolve_ms": t_resolve_ms,
                    "t_scan_ms": t_scan_ms,
                    "total_frames": n_frames,
                    "chunk_size": chunk_size,
                    "server_emit_ms": time.time() * 1000.0,
                }))

            start = 0
            while start < n_frames:
                if cancellation._event.is_set() or await request.is_disconnected():
                    return

                safe_count = min(chunk_size, n_frames - start)
                profile = {} if debug_timings else None

                def pack_chunk() -> tuple[int, str, float, float]:
                    cancellation.check()
                    t_pack_0 = time.perf_counter() if debug_timings else 0.0
                    payload = service.stream_frame_chunk_binary(
                        resolved, start, safe_count, format, summary, profile=profile,
                    )
                    cancellation.check()
                    header_size = struct.unpack_from("<I", payload, 4)[0]
                    header = json.loads(payload[8:8 + header_size])
                    actual_count = header["count"]
                    if header["start"] != start or not 0 < actual_count <= safe_count:
                        raise AppError("INVALID_FRAME_RANGE", "Stream chunk does not cover the requested frame range", 500)
                    t_pack_ms = (time.perf_counter() - t_pack_0) * 1000.0 if debug_timings else 0.0
                    t_b64_0 = time.perf_counter() if debug_timings else 0.0
                    encoded = base64.b64encode(payload).decode("ascii")
                    t_b64_ms = (time.perf_counter() - t_b64_0) * 1000.0 if debug_timings else 0.0
                    return actual_count, encoded, t_pack_ms, t_b64_ms

                try:
                    actual_count, encoded, t_pack_ms, t_b64_ms = await anyio.to_thread.run_sync(pack_chunk)
                except Exception as exc:
                    if not cancellation._event.is_set() and not await request.is_disconnected():
                        yield _sse_event("error", json.dumps({"code": "CHUNK_FAILED", "message": str(exc)}))
                    return

                if cancellation._event.is_set() or await request.is_disconnected():
                    return
                if debug_timings:
                    yield _sse_event("meta", json.dumps({
                        "start": start,
                        "count": actual_count,
                        "t_pack_ms": t_pack_ms,
                        "t_b64_ms": t_b64_ms,
                        "server_emit_ms": time.time() * 1000.0,
                        "size_b64": len(encoded),
                        "profile": profile,
                    }))
                yield _sse_event("chunk", encoded)
                del encoded
                start += actual_count

            if not cancellation._event.is_set() and not await request.is_disconnected():
                yield _sse_event("done", json.dumps({"n_frames": n_frames}))
        finally:
            cancellation.cancel()
            watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await watch_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event: str, data: str) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {data}\n\n"
