from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings, TerminalConfig, WorkspaceConfig
from backend.app.core.errors import AppError
from backend.app.core.security import WorkspaceSecurity
from backend.app.main import create_app
from backend.app.providers.terminal.base import TerminalProvider
from backend.app.providers.terminal.local_pty import LocalPtyTerminalProvider
from backend.app.services.terminal_service import TerminalManager, TerminalSession, utc_now


class FakeTerminalProvider(TerminalProvider):
    def __init__(self) -> None:
        self._shell = ""
        self.cwd = ""
        self.rows = 0
        self.cols = 0
        self.writes: list[str] = []
        self.alive = False

    @property
    def shell(self) -> str:
        return self._shell

    def start(self, cwd: str, rows: int, cols: int, shell: str | None = None) -> None:
        self.cwd = cwd
        self.rows = rows
        self.cols = cols
        self._shell = shell or "fake-shell"
        self.alive = True

    def write(self, data: str) -> None:
        self.writes.append(data)

    def read(self, size: int = 4096) -> str:
        return ""

    def resize(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols

    def terminate(self) -> None:
        self.alive = False

    def is_alive(self) -> bool:
        return self.alive


def test_terminal_config_defaults() -> None:
    settings = Settings()

    assert settings.terminal.enabled is True
    assert settings.terminal.max_sessions == 4
    assert settings.terminal.default_rows == 30
    assert settings.terminal.default_cols == 120
    assert settings.terminal.allow_sync_cwd is True


def test_windows_powershell_args_configure_interactive_encoding() -> None:
    provider = LocalPtyTerminalProvider()
    provider._shell = "powershell.exe"

    args = provider._shell_args()

    assert "-NoExit" in args
    assert "-NoProfile" in args
    assert "[Console]::InputEncoding" in args[-1]
    assert "Set-PSReadLineOption" in args[-1]


def test_terminal_session_sync_cwd_validates_workspace(tmp_path: Path) -> None:
    provider = FakeTerminalProvider()
    provider.start(str(tmp_path), 24, 80)
    created_at = utc_now()
    session = TerminalSession(
        session_id="term_test",
        provider=provider,
        cwd=str(tmp_path),
        created_at=created_at,
        last_active_at=created_at,
        security=WorkspaceSecurity(tmp_path),
        allow_sync_cwd=True,
    )
    subdir = tmp_path / "calc"
    subdir.mkdir()

    session.sync_cwd(str(subdir))

    assert session.cwd == str(subdir.resolve())
    assert provider.writes == [provider.build_cd_command(str(subdir.resolve()))]

    with pytest.raises(AppError) as exc:
        session.sync_cwd(str(tmp_path.parent))

    assert exc.value.code == "FORBIDDEN_PATH"


def test_terminal_manager_enforces_session_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(
        workspace=WorkspaceConfig(root=tmp_path),
        terminal=TerminalConfig(max_sessions=1, default_rows=33, default_cols=101),
    )
    manager = TerminalManager()

    session = manager.create_session(settings, None, None, None, None)

    assert session.cwd == str(tmp_path.resolve())
    assert session.provider.rows == 33
    assert session.provider.cols == 101

    with pytest.raises(AppError) as exc:
        manager.create_session(settings, None, None, None, None)

    assert exc.value.code == "TERMINAL_LIMIT_REACHED"
    manager.close_session(session.session_id)


def test_terminal_manager_releases_session_after_client_disconnect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(workspace=WorkspaceConfig(root=tmp_path))
    manager = TerminalManager()
    session = manager.create_session(settings, None, None, None, None)

    attached = manager.attach_client(session.session_id)
    manager.detach_client(session.session_id)

    assert attached.clients == 0
    assert attached.is_alive() is False
    assert manager.list_sessions() == []


def test_terminal_sessions_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(workspace=WorkspaceConfig(root=tmp_path))
    client = TestClient(create_app(settings))

    created = client.post("/api/terminal/sessions", json={"cwd": str(tmp_path), "rows": 20, "cols": 80})

    assert created.status_code == 200
    session_id = created.json()["session_id"]

    listed = client.get("/api/terminal/sessions")
    assert listed.status_code == 200
    assert any(item["session_id"] == session_id for item in listed.json()["items"])

    closed = client.delete(f"/api/terminal/sessions/{session_id}")
    assert closed.status_code == 200
    assert closed.json()["success"] is True
