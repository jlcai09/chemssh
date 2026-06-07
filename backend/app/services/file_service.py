from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.core.security import WorkspaceSecurity
from backend.app.models.file import (
    DirectoryListing,
    FileOperationResponse,
    FileReadResponse,
    MoveItemRequest,
    TailResponse,
)
from backend.app.providers.filesystem.local_fs import LocalFileSystemProvider
from backend.app.services.file_types import detect_preview


class FileService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.security = WorkspaceSecurity(settings.workspace.root)
        self.provider = LocalFileSystemProvider()

    def list_dir(self, raw_path: str | None = None) -> DirectoryListing:
        path = self.security.resolve_path(raw_path)
        listing = self.provider.list_dir(path)
        listing.parent = self._safe_parent(path)
        return listing

    def read_file(self, raw_path: str, *, force: bool = False) -> FileReadResponse:
        path = self.security.resolve_path(raw_path)
        max_bytes = None if force else self.settings.workspace.max_read_size_mb * 1024 * 1024
        content, encoding, size = self.provider.read_text_file(path, max_bytes)
        preview_type, fmt = detect_preview(path, is_dir=False)
        if preview_type == "file":
            preview_type = "text"
        return FileReadResponse(
            path=str(path),
            name=path.name,
            encoding=encoding,
            content=content,
            preview_type=preview_type,
            format=fmt,
            size=size,
        )

    def write_file(self, raw_path: str, content: str) -> FileOperationResponse:
        path = self.security.resolve_path(raw_path)
        self.provider.write_text_file(path, content)
        return FileOperationResponse(path=str(path), message="File saved")

    def tail_file(self, raw_path: str, lines: int | None = None) -> TailResponse:
        path = self.security.resolve_path(raw_path)
        requested_lines = lines or self.settings.logs.default_tail_lines
        safe_lines = min(max(requested_lines, 1), self.settings.logs.max_tail_lines)
        content, truncated = self.provider.tail_text_file(
            path,
            safe_lines,
            self.settings.logs.max_tail_bytes_mb * 1024 * 1024,
        )
        return TailResponse(path=str(path), lines=safe_lines, content=content, truncated=truncated)

    def delete_path(self, raw_path: str) -> FileOperationResponse:
        if not self.settings.workspace.allow_delete:
            raise AppError("DELETE_DISABLED", "Delete is disabled by configuration", 403)
        path = self.security.resolve_path(raw_path)
        if path == self.security.root:
            raise AppError("DELETE_WORKSPACE_ROOT", "Cannot delete workspace root", 400)
        self.provider.delete_path(path)
        return FileOperationResponse(path=str(path), message="Path deleted")

    def rename_path(self, raw_old_path: str, raw_new_path: str) -> FileOperationResponse:
        old_path = self.security.resolve_path(raw_old_path)
        new_path = self.security.resolve_path(raw_new_path)
        if old_path == self.security.root:
            raise AppError("RENAME_WORKSPACE_ROOT", "Cannot rename workspace root", 400)
        self.provider.rename_path(old_path, new_path)
        return FileOperationResponse(path=str(new_path), message="Path renamed")

    def move_paths(
        self,
        raw_paths: list[str],
        raw_target_directory: str,
        *,
        items: list[MoveItemRequest] | None = None,
    ) -> FileOperationResponse:
        raw_items = items or [MoveItemRequest(path=path) for path in raw_paths]
        if not raw_items:
            raise AppError("NO_PATHS", "移动失败：没有选择要移动的文件或文件夹", 400)

        target_directory = self.security.resolve_path(raw_target_directory)
        if not target_directory.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"移动失败：目标文件夹不存在：{target_directory}", 404)
        if not target_directory.is_dir():
            raise AppError("NOT_A_DIRECTORY", f"移动失败：目标路径不是文件夹：{target_directory}", 400)

        moves: list[tuple[Path, Path, bool]] = []
        seen_paths: set[Path] = set()
        destination_names: set[str] = set()
        for item in raw_items:
            path = self.security.resolve_path(item.path)
            if not path.exists():
                raise AppError("PATH_NOT_FOUND", f"移动失败：源路径不存在：{path}", 404)
            if path == self.security.root:
                raise AppError("MOVE_WORKSPACE_ROOT", f"移动失败：不能移动工作区根目录：{path}", 400)
            if path in seen_paths:
                continue
            if path == target_directory:
                raise AppError("MOVE_INTO_SELF", f"移动失败：不能把文件夹移动到它自身：{path}", 400)
            if path.is_dir() and self._path_contains(path, target_directory):
                raise AppError("MOVE_INTO_SELF", f"移动失败：不能把文件夹移动到它的子文件夹中。源路径：{path}；目标文件夹：{target_directory}", 400)

            target_name = self.security.validate_child_name(item.target_name or path.name, field="target name")
            destination = (target_directory / target_name).resolve(strict=False)
            if not self.security.is_allowed(destination):
                raise AppError("FORBIDDEN_PATH", f"移动失败：目标路径超出了工作区范围：{destination}", 403)
            if path == destination:
                raise AppError("MOVE_SAME_PATH", f"移动失败：源位置和目标位置相同：{path}", 400)
            if path.is_dir() and self._path_contains(path, destination):
                raise AppError("MOVE_INTO_SELF", f"移动失败：不能把文件夹移动到它自身或它的子文件夹中。源路径：{path}；目标路径：{destination}", 400)
            if target_name in destination_names:
                raise AppError("PATH_EXISTS", f"移动失败：多个源项目会移动成同一个目标名称：{target_name}", 409)
            if destination.exists() and not item.overwrite:
                raise AppError("PATH_EXISTS", f"移动失败：目标位置已存在同名项目：{destination}", 409)
            overwrite = item.overwrite and destination.exists()
            if overwrite and path.is_dir() != destination.is_dir():
                raise AppError("MOVE_TYPE_CONFLICT", f"移动失败：同名项目类型不同，不能覆盖：{destination}", 409)

            destination_names.add(target_name)
            seen_paths.add(path)
            moves.append((path, destination, overwrite))

        if all(destination.parent == target_directory and destination.name == path.name and not overwrite for path, destination, overwrite in moves):
            self.provider.move_paths([path for path, _, _ in moves], target_directory)
        else:
            for path, destination, overwrite in moves:
                self.provider.move_path_to(path, destination, overwrite=overwrite)
        return FileOperationResponse(path=str(target_directory), message="Paths moved")

    def copy_paths(
        self,
        raw_paths: list[str],
        raw_target_directory: str,
        *,
        items: list[MoveItemRequest] | None = None,
    ) -> FileOperationResponse:
        raw_items = items or [MoveItemRequest(path=path) for path in raw_paths]
        if not raw_items:
            raise AppError("NO_PATHS", "复制失败：没有选择要复制的文件或文件夹", 400)

        target_directory = self.security.resolve_path(raw_target_directory)
        if not target_directory.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"复制失败：目标文件夹不存在：{target_directory}", 404)
        if not target_directory.is_dir():
            raise AppError("NOT_A_DIRECTORY", f"复制失败：目标路径不是文件夹：{target_directory}", 400)

        copies: list[tuple[Path, Path, bool]] = []
        seen_paths: set[Path] = set()
        destination_names: set[str] = set()
        for item in raw_items:
            path = self.security.resolve_path(item.path)
            if not path.exists():
                raise AppError("PATH_NOT_FOUND", f"复制失败：源路径不存在：{path}", 404)
            if path == self.security.root:
                raise AppError("COPY_WORKSPACE_ROOT", f"复制失败：不能复制工作区根目录：{path}", 400)
            if path in seen_paths:
                continue
            if path.is_dir() and self._path_contains(path, target_directory):
                raise AppError("COPY_INTO_SELF", f"复制失败：不能把文件夹复制到它自身或它的子文件夹中。源路径：{path}；目标文件夹：{target_directory}", 400)

            target_name = self.security.validate_child_name(item.target_name or path.name, field="target name")
            destination = (target_directory / target_name).resolve(strict=False)
            if not self.security.is_allowed(destination):
                raise AppError("FORBIDDEN_PATH", f"复制失败：目标路径超出了工作区范围：{destination}", 403)
            if path == destination:
                raise AppError("COPY_SAME_PATH", f"复制失败：源位置和目标位置相同：{path}", 400)
            if path.is_dir() and self._path_contains(path, destination):
                raise AppError("COPY_INTO_SELF", f"复制失败：不能把文件夹复制到它自身或它的子文件夹中。源路径：{path}；目标路径：{destination}", 400)
            if target_name in destination_names:
                raise AppError("PATH_EXISTS", f"复制失败：多个源项目会复制成同一个目标名称：{target_name}", 409)
            if destination.exists() and not item.overwrite:
                raise AppError("PATH_EXISTS", f"复制失败：目标位置已存在同名项目：{destination}", 409)
            overwrite = item.overwrite and destination.exists()
            if overwrite and path.is_dir() != destination.is_dir():
                raise AppError("COPY_TYPE_CONFLICT", f"复制失败：同名项目类型不同，不能覆盖：{destination}", 409)

            destination_names.add(target_name)
            seen_paths.add(path)
            copies.append((path, destination, overwrite))

        for path, destination, overwrite in copies:
            self.provider.copy_path_to(path, destination, overwrite=overwrite)
        return FileOperationResponse(path=str(target_directory), message="Paths copied")

    def make_directory(self, raw_path: str, name: str) -> FileOperationResponse:
        target = self.security.resolve_child(raw_path, name, field="directory name")
        self.provider.make_directory(target)
        return FileOperationResponse(path=str(target), message="Directory created")

    async def save_upload(self, raw_path: str, upload: Any, relative_path: str | None = None) -> FileOperationResponse:
        directory = self.security.resolve_path(raw_path)
        if not directory.exists() or not directory.is_dir():
            raise AppError("DIRECTORY_NOT_FOUND", f"Upload directory not found: {directory}", 404)
        target = self._resolve_upload_target(directory, relative_path or upload.filename)
        max_bytes = self.settings.workspace.max_upload_size_mb * 1024 * 1024
        total = 0

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        handle.close()
                        target.unlink(missing_ok=True)
                        raise AppError(
                            "UPLOAD_TOO_LARGE",
                            f"Upload exceeds {self.settings.workspace.max_upload_size_mb} MB",
                            413,
                        )
                    handle.write(chunk)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot upload to: {target}", 403) from exc

        return FileOperationResponse(path=str(target), message="File uploaded")

    def _resolve_upload_target(self, directory: Path, relative_path: str) -> Path:
        normalized = relative_path.replace("\\", "/").strip("/")
        if not normalized:
            raise AppError("INVALID_NAME", "Invalid upload path", 400)

        candidate_path = Path(normalized)
        if candidate_path.is_absolute():
            raise AppError("INVALID_NAME", f"Invalid upload path: {relative_path}", 400)

        parts: list[str] = []
        for part in candidate_path.parts:
            if part in {"", ".", ".."}:
                raise AppError("INVALID_NAME", f"Invalid upload path: {relative_path}", 400)
            parts.append(self.security.validate_child_name(part, field="upload path segment"))

        target = directory.joinpath(*parts).resolve(strict=False)
        if not self.security.is_allowed(target):
            raise AppError("FORBIDDEN_PATH", f"Path is outside workspace root: {relative_path}", 403)
        if target.exists() and target.is_dir():
            raise AppError("NOT_A_FILE", f"Upload target is a directory: {target}", 400)
        return target

    def resolve_download(self, raw_path: str) -> Path:
        path = self.security.resolve_path(raw_path)
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", f"File not found: {path}", 404)
        if not path.is_file():
            raise AppError("NOT_A_FILE", f"Path is not a file: {path}", 400)
        return path

    def create_download_archive(self, raw_paths: list[str]) -> Path:
        if not raw_paths:
            raise AppError("NO_PATHS", "No paths selected", 400)

        paths: list[Path] = []
        seen_paths: set[Path] = set()
        for raw_path in raw_paths:
            path = self.security.resolve_path(raw_path)
            if not path.exists():
                raise AppError("PATH_NOT_FOUND", f"Path not found: {path}", 404)
            if path in seen_paths:
                continue
            seen_paths.add(path)
            paths.append(path)

        temp_file = tempfile.NamedTemporaryFile(prefix="chemssh-download-", suffix=".zip", delete=False)
        archive_path = Path(temp_file.name)
        temp_file.close()

        root = self.security.root
        added_entries: set[str] = set()

        def add_directory(archive: zipfile.ZipFile, directory: Path) -> None:
            if directory == root:
                return
            arcname = directory.relative_to(root).as_posix().rstrip("/") + "/"
            if arcname in added_entries:
                return
            archive.writestr(arcname, b"")
            added_entries.add(arcname)

        def add_file(archive: zipfile.ZipFile, file_path: Path) -> None:
            arcname = file_path.relative_to(root).as_posix()
            if arcname in added_entries:
                return
            archive.write(file_path, arcname)
            added_entries.add(arcname)

        try:
            with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in paths:
                    if path.is_file():
                        add_file(archive, path)
                        continue

                    descendants = sorted(path.rglob("*"), key=lambda item: item.as_posix())
                    add_directory(archive, path)
                    for descendant in descendants:
                        if descendant.is_dir():
                            add_directory(archive, descendant)
                        elif descendant.is_file():
                            add_file(archive, descendant)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise

        return archive_path

    def _safe_parent(self, path: Path) -> str | None:
        parent = path.parent.resolve(strict=False)
        if path == self.security.root or not self.security.is_allowed(parent):
            return None
        return str(parent)

    def _path_contains(self, parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False
