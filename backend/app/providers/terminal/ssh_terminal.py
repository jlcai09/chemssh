from __future__ import annotations

from backend.app.providers.terminal.base import TerminalProvider


class SshTerminalProvider(TerminalProvider):
    @property
    def shell(self) -> str:
        return "ssh"

    def start(self, cwd: str, rows: int, cols: int, shell: str | None = None) -> None:
        raise NotImplementedError("SSH terminal provider is reserved for a future implementation")

    def write(self, data: str) -> None:
        raise NotImplementedError("SSH terminal provider is reserved for a future implementation")

    def read(self, size: int = 4096) -> str:
        raise NotImplementedError("SSH terminal provider is reserved for a future implementation")

    def resize(self, rows: int, cols: int) -> None:
        raise NotImplementedError("SSH terminal provider is reserved for a future implementation")

    def terminate(self) -> None:
        raise NotImplementedError("SSH terminal provider is reserved for a future implementation")

    def is_alive(self) -> bool:
        return False
