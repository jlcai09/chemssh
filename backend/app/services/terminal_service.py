from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.core.security import WorkspaceSecurity
from backend.app.models.terminal import TerminalSessionResponse
from backend.app.providers.terminal.base import TerminalProvider
from backend.app.providers.terminal.local_pty import LocalPtyTerminalProvider


CWD_MARKER_PREFIX = "\x1b]633;P;Cwd="


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TerminalSession:
    session_id: str
    provider: TerminalProvider
    cwd: str
    created_at: datetime
    last_active_at: datetime
    security: WorkspaceSecurity
    allow_sync_cwd: bool
    clients: int = 0
    _pending_cwd: str | None = field(default=None, init=False, repr=False)
    _cwd_marker_buffer: str = field(default="", init=False, repr=False)

    @property
    def shell(self) -> str:
        return self.provider.shell

    def read(self, size: int = 4096) -> str:
        data = self.provider.read(size)
        if data:
            self.touch()
            return self._extract_cwd_markers(data)
        return self._extract_cwd_markers("")

    def write(self, data: str) -> None:
        self.provider.write(data)
        self.touch()

    def resize(self, rows: int, cols: int) -> None:
        self.provider.resize(rows, cols)
        self.touch()

    def sync_cwd(self, raw_path: str) -> None:
        if not self.allow_sync_cwd:
            raise AppError("TERMINAL_SYNC_DISABLED", "Terminal cwd sync is disabled", 403)

        path = self.security.resolve_path(raw_path)
        if not path.exists() or not path.is_dir():
            raise AppError("NOT_A_DIRECTORY", f"Terminal cwd is not a directory: {path}", 400)

        self.provider.write_control(self.provider.build_cd_command(str(path)))
        self.cwd = str(path)
        self.touch()

    def consume_cwd_update(self) -> str | None:
        cwd = self._pending_cwd
        self._pending_cwd = None
        return cwd

    def _extract_cwd_markers(self, data: str) -> str:
        if not data and not self._cwd_marker_buffer:
            return ""

        text = self._cwd_marker_buffer + data
        self._cwd_marker_buffer = ""
        parts: list[str] = []
        index = 0
        while index < len(text):
            start = text.find(CWD_MARKER_PREFIX, index)
            if start < 0:
                remaining, pending = _split_possible_marker_prefix(text[index:])
                parts.append(remaining)
                self._cwd_marker_buffer = pending
                break

            parts.append(text[index:start])
            value_start = start + len(CWD_MARKER_PREFIX)
            bel_end = text.find("\x07", value_start)
            st_end = text.find("\x1b\\", value_start)
            end, terminator_length = _first_marker_end(bel_end, st_end)
            if end < 0:
                self._cwd_marker_buffer = text[start:]
                break

            self._accept_cwd_marker(text[value_start:end])
            index = end + terminator_length

        return "".join(parts)

    def _accept_cwd_marker(self, raw_path: str) -> None:
        try:
            path = self.security.resolve_path(raw_path)
        except AppError:
            return
        if not path.exists() or not path.is_dir():
            return
        normalized = str(path)
        if normalized == self.cwd:
            return
        self.cwd = normalized
        self._pending_cwd = normalized
        self.touch()

    def close(self) -> None:
        self.provider.terminate()
        self.touch()

    def attach_client(self) -> None:
        self.clients += 1
        self.touch()

    def detach_client(self) -> int:
        self.clients = max(self.clients - 1, 0)
        self.touch()
        return self.clients

    def is_alive(self) -> bool:
        return self.provider.is_alive()

    def touch(self) -> None:
        self.last_active_at = utc_now()

    def to_response(self) -> TerminalSessionResponse:
        return TerminalSessionResponse(
            session_id=self.session_id,
            cwd=self.cwd,
            shell=self.shell,
            created_at=self.created_at,
            last_active_at=self.last_active_at,
            alive=self.is_alive(),
            clients=self.clients,
        )


class TerminalManager:
    def __init__(self) -> None:
        self.sessions: dict[str, TerminalSession] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        settings: Settings,
        cwd: str | None,
        shell: str | None,
        rows: int | None,
        cols: int | None,
    ) -> TerminalSession:
        if not settings.terminal.enabled:
            raise AppError("TERMINAL_DISABLED", "Terminal is disabled by configuration", 403)

        with self._lock:
            self._prune_closed_sessions()
            if self._alive_count() >= settings.terminal.max_sessions:
                raise AppError("TERMINAL_LIMIT_REACHED", "Terminal session limit reached", 429)

            security = WorkspaceSecurity(settings.workspace.root)
            safe_cwd = security.resolve_path(cwd)
            if not safe_cwd.exists() or not safe_cwd.is_dir():
                raise AppError("NOT_A_DIRECTORY", f"Terminal cwd is not a directory: {safe_cwd}", 400)

            provider = LocalPtyTerminalProvider()
            session_id = f"term_{uuid.uuid4().hex[:12]}"
            started_at = utc_now()
            try:
                provider.start(
                    str(safe_cwd),
                    rows or settings.terminal.default_rows,
                    cols or settings.terminal.default_cols,
                    shell or settings.terminal.shell,
                )
            except ImportError as exc:
                raise AppError("TERMINAL_DEPENDENCY_MISSING", "ptyprocess is required for terminal support", 500) from exc
            except FileNotFoundError as exc:
                raise AppError("TERMINAL_SHELL_NOT_FOUND", f"Terminal shell not found: {shell}", 400) from exc
            except Exception as exc:
                provider.terminate()
                raise AppError("TERMINAL_START_FAILED", f"Terminal failed to start: {exc}", 500) from exc

            session = TerminalSession(
                session_id=session_id,
                provider=provider,
                cwd=str(safe_cwd),
                created_at=started_at,
                last_active_at=started_at,
                security=security,
                allow_sync_cwd=settings.terminal.allow_sync_cwd,
            )
            self.sessions[session_id] = session
            return session

    def get_session(self, session_id: str) -> TerminalSession:
        with self._lock:
            session = self.sessions.get(session_id)
        if session is None:
            raise AppError("TERMINAL_SESSION_NOT_FOUND", f"Terminal session not found: {session_id}", 404)
        return session

    def close_session(self, session_id: str) -> None:
        with self._lock:
            session = self.sessions.pop(session_id, None)
        if session is None:
            raise AppError("TERMINAL_SESSION_NOT_FOUND", f"Terminal session not found: {session_id}", 404)
        session.close()

    def attach_client(self, session_id: str) -> TerminalSession:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                raise AppError("TERMINAL_SESSION_NOT_FOUND", f"Terminal session not found: {session_id}", 404)
            session.attach_client()
            return session

    def detach_client(self, session_id: str) -> None:
        with self._lock:
            session = self.sessions.get(session_id)
            if session is None:
                return
            remaining_clients = session.detach_client()
            if remaining_clients > 0:
                return
            self.sessions.pop(session_id, None)
        session.close()

    def list_sessions(self) -> list[TerminalSessionResponse]:
        with self._lock:
            sessions = sorted(self.sessions.values(), key=lambda item: item.created_at)
        return [session.to_response() for session in sessions]

    def _alive_count(self) -> int:
        return sum(1 for session in self.sessions.values() if session.is_alive())

    def _prune_closed_sessions(self) -> None:
        closed = [session_id for session_id, session in self.sessions.items() if not session.is_alive()]
        for session_id in closed:
            self.sessions.pop(session_id, None)


terminal_manager = TerminalManager()


def _first_marker_end(bel_end: int, st_end: int) -> tuple[int, int]:
    candidates: list[tuple[int, int]] = []
    if bel_end >= 0:
        candidates.append((bel_end, 1))
    if st_end >= 0:
        candidates.append((st_end, 2))
    return min(candidates, default=(-1, 0), key=lambda item: item[0])


def _split_possible_marker_prefix(text: str) -> tuple[str, str]:
    max_length = min(len(CWD_MARKER_PREFIX) - 1, len(text))
    for length in range(max_length, 0, -1):
        suffix = text[-length:]
        if CWD_MARKER_PREFIX.startswith(suffix):
            return text[:-length], suffix
    return text, ""
