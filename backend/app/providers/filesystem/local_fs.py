from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.errors import AppError
from backend.app.models.file import DirectoryListing, FileItem
from backend.app.providers.filesystem.base import FileSystemProvider
from backend.app.services.file_types import detect_preview


def _mtime_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


class LocalFileSystemProvider(FileSystemProvider):
    def list_dir(self, path: Path) -> DirectoryListing:
        if not path.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"Directory not found: {path}", 404)
        if not path.is_dir():
            raise AppError("NOT_A_DIRECTORY", f"Path is not a directory: {path}", 400)

        entries: list[tuple[bool, str, FileItem]] = []
        try:
            with os.scandir(path) as children:
                for child in children:
                    try:
                        is_dir = child.is_dir()
                        stat = child.stat()
                    except OSError:
                        continue

                    child_path = Path(child.path)
                    preview_type, fmt = detect_preview(child_path, is_dir=is_dir)
                    entries.append(
                        (
                            not is_dir,
                            child.name.lower(),
                            FileItem(
                                name=child.name,
                                path=child.path,
                                type="directory" if is_dir else "file",
                                size=None if is_dir else stat.st_size,
                                mtime=_mtime_iso(stat.st_mtime),
                                extension="" if is_dir else child_path.suffix.lower(),
                                preview_type=preview_type,
                                format=fmt,
                            ),
                        )
                    )
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot list directory: {path}", 403) from exc

        items = [item for _, _, item in sorted(entries, key=lambda entry: (entry[0], entry[1]))]

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

    def move_paths(self, paths: list[Path], target_directory: Path) -> None:
        if not paths:
            raise AppError("NO_PATHS", "移动失败：没有选择要移动的文件或文件夹", 400)
        if not target_directory.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"移动失败：目标文件夹不存在：{target_directory}", 404)
        if not target_directory.is_dir():
            raise AppError("NOT_A_DIRECTORY", f"移动失败：目标不是文件夹：{target_directory}", 400)

        for path in paths:
            if not path.exists():
                raise AppError("PATH_NOT_FOUND", f"移动失败：源路径不存在：{path}", 404)

        mv = shutil.which("mv")
        if mv:
            command = [mv, "--", *[str(path) for path in paths], str(target_directory)]
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=False)
            except PermissionError as exc:
                raise AppError("PERMISSION_DENIED", self._move_error_message(paths, target_directory, "权限不足，无法执行移动操作"), 403) from exc
            if result.returncode != 0:
                reason = result.stderr.strip() or result.stdout.strip() or f"mv 命令退出码为 {result.returncode}"
                raise AppError("MOVE_FAILED", self._move_error_message(paths, target_directory, reason), 500)
            return

        try:
            for path in paths:
                path.rename(target_directory / path.name)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", self._move_error_message(paths, target_directory, "权限不足，无法执行移动操作"), 403) from exc
        except OSError as exc:
            raise AppError("MOVE_FAILED", self._move_error_message(paths, target_directory, self._os_error_reason(exc)), 500) from exc

    def move_path_to(self, path: Path, destination: Path, *, overwrite: bool = False) -> None:
        if not path.exists():
            raise AppError("PATH_NOT_FOUND", f"移动失败：源路径不存在：{path}", 404)
        if destination.exists():
            if not overwrite:
                raise AppError("PATH_EXISTS", f"移动失败：目标位置已存在同名项目：{destination}", 409)
            self._merge_or_replace_path(path, destination)
            return

        if not destination.parent.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"移动失败：目标文件夹不存在：{destination.parent}", 404)
        self._native_mv(path, destination, force=False)

    def _merge_or_replace_path(self, source: Path, destination: Path) -> None:
        if source.is_dir():
            if not destination.is_dir():
                raise AppError("MOVE_TYPE_CONFLICT", f"移动失败：不能用文件夹覆盖同名文件：{destination}", 409)
            try:
                children = sorted(source.iterdir(), key=lambda item: item.name.lower())
            except PermissionError as exc:
                raise AppError("PERMISSION_DENIED", f"移动失败：权限不足，无法读取源文件夹内容：{source}", 403) from exc
            for child in children:
                self.move_path_to(child, destination / child.name, overwrite=True)
            try:
                source.rmdir()
            except PermissionError as exc:
                raise AppError("PERMISSION_DENIED", f"移动失败：权限不足，无法移除已合并的源文件夹：{source}", 403) from exc
            except OSError as exc:
                raise AppError("MOVE_FAILED", self._move_error_message([source], destination, self._os_error_reason(exc)), 500) from exc
            return

        if destination.is_dir():
            raise AppError("MOVE_TYPE_CONFLICT", f"移动失败：不能用文件覆盖同名文件夹：{destination}", 409)
        self._native_mv(source, destination, force=True)

    def _native_mv(self, source: Path, destination: Path, *, force: bool) -> None:
        mv = shutil.which("mv")
        if mv:
            command = [mv]
            if force:
                command.append("-f")
            command.extend(["--", str(source), str(destination)])
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=False)
            except PermissionError as exc:
                raise AppError("PERMISSION_DENIED", self._move_error_message([source], destination, "权限不足，无法执行移动操作"), 403) from exc
            if result.returncode != 0:
                reason = result.stderr.strip() or result.stdout.strip() or f"mv 命令退出码为 {result.returncode}"
                raise AppError("MOVE_FAILED", self._move_error_message([source], destination, reason), 500)
            return

        try:
            if force:
                source.replace(destination)
            else:
                source.rename(destination)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", self._move_error_message([source], destination, "权限不足，无法执行移动操作"), 403) from exc
        except OSError as exc:
            raise AppError("MOVE_FAILED", self._move_error_message([source], destination, self._os_error_reason(exc)), 500) from exc

    def _move_error_message(self, sources: list[Path], destination: Path, reason: str) -> str:
        source_label = "、".join(str(path) for path in sources[:3])
        if len(sources) > 3:
            source_label = f"{source_label} 等 {len(sources)} 个项目"
        reason_label = reason.strip() or "未知错误"
        return f"移动失败：无法将「{source_label}」移动到「{destination}」。原因：{reason_label}"

    def copy_path_to(self, path: Path, destination: Path, *, overwrite: bool = False) -> None:
        if not path.exists():
            raise AppError("PATH_NOT_FOUND", f"复制失败：源路径不存在：{path}", 404)
        if destination.exists():
            if not overwrite:
                raise AppError("PATH_EXISTS", f"复制失败：目标位置已存在同名项目：{destination}", 409)
            self._merge_or_replace_copy(path, destination)
            return

        if not destination.parent.exists():
            raise AppError("DIRECTORY_NOT_FOUND", f"复制失败：目标文件夹不存在：{destination.parent}", 404)
        self._copy_new_path(path, destination)

    def _merge_or_replace_copy(self, source: Path, destination: Path) -> None:
        if source.is_dir():
            if not destination.is_dir():
                raise AppError("COPY_TYPE_CONFLICT", f"复制失败：不能用文件夹覆盖同名文件：{destination}", 409)
            try:
                children = sorted(source.iterdir(), key=lambda item: item.name.lower())
            except PermissionError as exc:
                raise AppError("PERMISSION_DENIED", f"复制失败：权限不足，无法读取源文件夹内容：{source}", 403) from exc
            for child in children:
                self.copy_path_to(child, destination / child.name, overwrite=True)
            return

        if destination.is_dir():
            raise AppError("COPY_TYPE_CONFLICT", f"复制失败：不能用文件覆盖同名文件夹：{destination}", 409)
        self._copy_new_path(source, destination, overwrite=True)

    def _copy_new_path(self, source: Path, destination: Path, *, overwrite: bool = False) -> None:
        try:
            if source.is_dir():
                shutil.copytree(source, destination, copy_function=shutil.copy2)
            else:
                if overwrite:
                    shutil.copy2(source, destination)
                else:
                    shutil.copy2(source, destination)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", self._copy_error_message([source], destination, "权限不足，无法执行复制操作"), 403) from exc
        except OSError as exc:
            raise AppError("COPY_FAILED", self._copy_error_message([source], destination, self._os_error_reason(exc)), 500) from exc

    def _copy_error_message(self, sources: list[Path], destination: Path, reason: str) -> str:
        source_label = "、".join(str(path) for path in sources[:3])
        if len(sources) > 3:
            source_label = f"{source_label} 等 {len(sources)} 个项目"
        reason_label = reason.strip() or "未知错误"
        return f"复制失败：无法将「{source_label}」复制到「{destination}」。原因：{reason_label}"

    def _os_error_reason(self, exc: OSError) -> str:
        if exc.strerror:
            return exc.strerror
        return str(exc) or "文件系统返回未知错误"

    def make_directory(self, path: Path) -> None:
        if path.exists():
            raise AppError("PATH_EXISTS", f"Path already exists: {path}", 409)
        try:
            path.mkdir(parents=False)
        except PermissionError as exc:
            raise AppError("PERMISSION_DENIED", f"Cannot create directory: {path}", 403) from exc
