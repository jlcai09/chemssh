from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.models.file import DirectoryListing


class FileSystemProvider(ABC):
    @abstractmethod
    def list_dir(self, path: Path) -> DirectoryListing:
        raise NotImplementedError

    @abstractmethod
    def read_text_file(self, path: Path, max_bytes: int | None) -> tuple[str, str, int]:
        raise NotImplementedError

    @abstractmethod
    def write_text_file(self, path: Path, content: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def tail_text_file(self, path: Path, lines: int, max_bytes: int) -> tuple[str, bool]:
        raise NotImplementedError

    @abstractmethod
    def delete_path(self, path: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def rename_path(self, old_path: Path, new_path: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def make_directory(self, path: Path) -> None:
        raise NotImplementedError
