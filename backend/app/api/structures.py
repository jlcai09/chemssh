from __future__ import annotations

from typing import Callable, Optional, TypeVar

import anyio
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from backend.app.dependencies import get_structure_service
from backend.app.models.structure import AseFrame, AseFrameChunkResponse, AsePreviewResponse
from backend.app.services.structure_service import STRUCTURE_BINARY_MEDIA_TYPE, StructureCancellationToken, StructureService


router = APIRouter(prefix="/structures", tags=["structures"])
T = TypeVar("T")


async def run_with_disconnect_cancellation(request: Request, operation: Callable[[StructureCancellationToken], T]) -> T:
    cancellation = StructureCancellationToken()
    result: T | None = None
    error: BaseException | None = None

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
        except BaseException as exc:
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
