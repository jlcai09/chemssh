from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.errors import AppError
from backend.app.models.file import DirectoryListing, FileItem
from backend.app.providers.filesystem.base import FileSystemProvider
from backend.app.services.file_types import detect_preview


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


class LocalFileSystemProvider(FileSystemProvider):
    def list_dir(self, path: Path) -> DirectoryListing:
        if not path.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"Directory not found: {path}", 404)
        if not path.is_dir():
            raise AppError("NOT_A_DIRECTORY", f"Path is not a directory: {path}", 400)

        items: list[FileItem] = []
        try:
            children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for child in children:
                try:
                    stat = child.stat()
                except OSError:
                    continue
                is_dir = child.is_dir()
                preview_type, fmt = detect_preview(child, is_dir=is_dir)
                items.append(
                    FileItem(
                        name=child.name,
                        path=str(child),
                        type="directory" if is_dir else "file",
                        size=None if is_dir else stat.st_size,
                        mtime=_mtime_iso(child),
                        extension="" if is_dir else child.suffix.lower(),
                        preview_type=preview_type,
                        format=fmt,
                    )
                )
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot list directory: {path}", 403) from exc

        return DirectoryListing(
            path=str(path),
            parent=str(path.parent) if path.parent != path else None,
            items=items,
        )

    def read_text_file(self, path: Path, max_bytes: int | None) -> tuple[str, str, int]:
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", f"File not found: {path}", 404)
        if not path.is_file():
            raise AppError("NOT_A_FILE", f"Path is not a file: {path}", 400)

        size = path.stat().st_size
        if max_bytes is not None and size > max_bytes:
            raise AppError(
                "FILE_TOO_LARGE",
                f"File is {size} bytes; use tail or download for files larger than {max_bytes} bytes",
                413,
            )

        try:
            data = path.read_bytes()
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot read file: {path}", 403) from exc

        try:
            return data.decode("utf-8"), "utf-8", size
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace"), "utf-8-replace", size

    def write_text_file(self, path: Path, content: str) -> None:
        if path.exists() and path.is_dir():
            raise AppError("NOT_A_FILE", f"Path is a directory: {path}", 400)
        if not path.parent.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"Parent directory not found: {path.parent}", 404)
        try:
            path.write_bytes(content.encode("utf-8"))
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot write file: {path}", 403) from exc

    def tail_text_file(self, path: Path, lines: int, max_bytes: int) -> tuple[str, bool]:
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", f"File not found: {path}", 404)
        if not path.is_file():
            raise AppError("NOT_A_FILE", f"Path is not a file: {path}", 400)
        if lines <= 0:
            return "", False

        block_size = 8192
        data = bytearray()
        truncated = False
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                remaining = handle.tell()
                while remaining > 0 and data.count(b"\n") <= lines:
                    read_size = min(block_size, remaining)
                    remaining -= read_size
                    handle.seek(remaining)
                    data[:0] = handle.read(read_size)
                    if len(data) >= max_bytes:
                        truncated = True
                        break
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot read file: {path}", 403) from exc

        raw_lines = bytes(data).splitlines()[-lines:]
        text = b"\n".join(raw_lines).decode("utf-8", errors="replace")
        if data.endswith(b"\n"):
            text += "\n"
        return text, truncated

    def delete_path(self, path: Path) -> None:
        if not path.exists():
            raise AppError("PATH_NOT_FOUND", f"Path not found: {path}", 404)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot delete path: {path}", 403) from exc

    def rename_path(self, old_path: Path, new_path: Path) -> None:
        if not old_path.exists():
            raise AppError("PATH_NOT_FOUND", f"Path not found: {old_path}", 404)
        if new_path.exists():
            raise AppError("PATH_EXISTS", f"Target already exists: {new_path}", 409)
        if not new_path.parent.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"Parent directory not found: {new_path.parent}", 404)
        try:
            old_path.rename(new_path)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot rename path: {old_path}", 403) from exc

    def make_directory(self, path: Path) -> None:
        if path.exists():
            raise AppError("PATH_EXISTS", f"Path already exists: {path}", 409)
        try:
            path.mkdir(parents=False)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot create directory: {path}", 403) from exc
