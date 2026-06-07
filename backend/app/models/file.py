from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


FileKind = Literal["file", "directory"]
PreviewType = Literal["text", "structure", "file", "directory"]


class FileItem(BaseModel):
    name: str
    path: str
    type: FileKind
    size: Optional[int] = None
    mtime: str
    extension: str = ""
    preview_type: PreviewType = "file"
    format: Optional[str] = None


class DirectoryListing(BaseModel):
    path: str
    parent: Optional[str] = None
    items: list[FileItem]


class FileReadResponse(BaseModel):
    path: str
    name: str
    encoding: str
    content: str
    preview_type: PreviewType
    format: Optional[str] = None
    size: int


class WriteFileRequest(BaseModel):
    path: str
    content: str


class RenameRequest(BaseModel):
    old_path: str
    new_path: str


class MoveItemRequest(BaseModel):
    path: str
    target_name: Optional[str] = None
    overwrite: bool = False


class MoveRequest(BaseModel):
    paths: list[str] = []
    target_directory: str
    items: list[MoveItemRequest] = []


class CopyRequest(BaseModel):
    paths: list[str] = []
    target_directory: str
    items: list[MoveItemRequest] = []


class CreateDirectoryRequest(BaseModel):
    path: str
    name: str


class DownloadArchiveRequest(BaseModel):
    paths: list[str]


class FileOperationResponse(BaseModel):
    success: bool = True
    path: Optional[str] = None
    message: str


class TailResponse(BaseModel):
    path: str
    lines: int
    content: str
    truncated: bool = False
