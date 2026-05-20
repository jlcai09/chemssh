from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from backend.app.dependencies import get_structure_service
from backend.app.models.structure import AseFrame, AsePreviewResponse
from backend.app.services.structure_service import STRUCTURE_BINARY_MEDIA_TYPE, StructureService


router = APIRouter(prefix="/structures", tags=["structures"])


@router.get("/ase/preview", response_model=AsePreviewResponse)
def read_ase_preview(
    path: str,
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    service: StructureService = Depends(get_structure_service),
) -> AsePreviewResponse:
    return service.preview(path, format, force=force)


@router.get("/ase/frame", response_model=AseFrame)
def read_ase_frame(
    path: str,
    index: int = Query(ge=0),
    format: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
    service: StructureService = Depends(get_structure_service),
) -> AseFrame:
    return service.read_frame(path, index, format, force=force)


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
