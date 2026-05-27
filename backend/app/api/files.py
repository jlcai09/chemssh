from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from backend.app.dependencies import get_file_service
from backend.app.core.errors import AppError
from backend.app.models.file import (
    CreateDirectoryRequest,
    DirectoryListing,
    DownloadArchiveRequest,
    FileOperationResponse,
    FileReadResponse,
    RenameRequest,
    TailResponse,
    WriteFileRequest,
)
from backend.app.services.file_service import FileService


router = APIRouter(prefix="/files", tags=["files"])


@router.get("/list", response_model=DirectoryListing)
def list_files(
    path: Optional[str] = Query(default=None),
    service: FileService = Depends(get_file_service),
) -> DirectoryListing:
    return service.list_dir(path)


@router.get("/read", response_model=FileReadResponse)
def read_file(
    path: str,
    force: bool = Query(default=False),
    service: FileService = Depends(get_file_service),
) -> FileReadResponse:
    return service.read_file(path, force=force)


@router.post("/write", response_model=FileOperationResponse)
def write_file(
    payload: WriteFileRequest,
    service: FileService = Depends(get_file_service),
) -> FileOperationResponse:
    return service.write_file(payload.path, payload.content)


@router.delete("/delete", response_model=FileOperationResponse)
def delete_file(path: str, service: FileService = Depends(get_file_service)) -> FileOperationResponse:
    return service.delete_path(path)


@router.post("/rename", response_model=FileOperationResponse)
def rename_file(
    payload: RenameRequest,
    service: FileService = Depends(get_file_service),
) -> FileOperationResponse:
    return service.rename_path(payload.old_path, payload.new_path)


@router.post("/mkdir", response_model=FileOperationResponse)
def create_directory(
    payload: CreateDirectoryRequest,
    service: FileService = Depends(get_file_service),
) -> FileOperationResponse:
    return service.make_directory(payload.path, payload.name)


@router.post("/upload", response_model=FileOperationResponse)
async def upload_file(
    path: str = Form(...),
    file: UploadFile = File(...),
    service: FileService = Depends(get_file_service),
) -> FileOperationResponse:
    return await service.save_upload(path, file)


@router.get("/download")
def download_file(path: str, service: FileService = Depends(get_file_service)) -> FileResponse:
    target = service.resolve_download(path)
    return FileResponse(target, filename=target.name)


@router.post("/download-archive")
def download_archive(
    payload: DownloadArchiveRequest,
    service: FileService = Depends(get_file_service),
) -> FileResponse:
    archive = service.create_download_archive(payload.paths)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename="chemweb-selection.zip",
        background=BackgroundTask(lambda: archive.unlink(missing_ok=True)),
    )


@router.get("/download-selection")
def download_selection(
    path: list[str] = Query(...),
    service: FileService = Depends(get_file_service),
) -> FileResponse:
    if len(path) == 1:
        try:
            target = service.resolve_download(path[0])
            return FileResponse(target, filename=target.name)
        except AppError:
            pass

    archive = service.create_download_archive(path)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename="chemweb-selection.zip",
        background=BackgroundTask(lambda: archive.unlink(missing_ok=True)),
    )


@router.get("/tail", response_model=TailResponse)
def tail_file(
    path: str,
    lines: Optional[int] = Query(default=None, ge=1),
    service: FileService = Depends(get_file_service),
) -> TailResponse:
    return service.tail_file(path, lines)
