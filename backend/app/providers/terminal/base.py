from __future__ import annotations

import shlex
from abc import ABC, abstractmethod


class TerminalProvider(ABC):
    @abstractmethod
    def start(self, cwd: str, rows: int, cols: int, shell: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def write(self, data: str) -> None:
        raise NotImplementedError

    def write_control(self, data: str) -> None:
        self.write(data)

    @abstractmethod
    def read(self, size: int = 4096) -> str:
        raise NotImplementedError

    @abstractmethod
    def resize(self, rows: int, cols: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def terminate(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_alive(self) -> bool:
        raise NotImplementedError

    @property
    @abstractmethod
    def shell(self) -> str:
        raise NotImplementedError

    def build_cd_command(self, path: str) -> str:
        return f"cd -- {shlex.quote(path)}\n"

    def exit_code(self) -> int | None:
        return None
