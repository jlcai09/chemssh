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
from backend.app.services.terminal_service import TerminalManager, TerminalSession, terminal_manager, utc_now


CLIENT_A = "client_test_a"
CLIENT_B = "client_test_b"
CLIENT_A_HEADERS = {"X-ChemSSH-Client-Id": CLIENT_A}
CLIENT_B_HEADERS = {"X-ChemSSH-Client-Id": CLIENT_B}


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
    assert settings.terminal.idle_timeout_seconds == 3600
    assert settings.terminal.allow_sync_cwd is True


def test_windows_powershell_args_configure_interactive_encoding() -> None:
    provider = LocalPtyTerminalProvider()
    provider._shell = "powershell.exe"

    args = provider._shell_args()

    assert "-NoExit" in args
    assert "-NoProfile" in args
    assert "[Console]::InputEncoding" in args[-1]
    assert "Set-PSReadLineOption" in args[-1]


def test_terminal_shims_include_vim_terminal_probe_workaround(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPtyTerminalProvider()

    def fake_mkdtemp(prefix: str) -> str:
        path = tmp_path / prefix.rstrip("-")
        path.mkdir()
        return str(path)

    monkeypatch.setattr("backend.app.providers.terminal.local_pty.tempfile.mkdtemp", fake_mkdtemp)

    shim_dir = provider._ensure_transfer_shims()

    for command in ("vi", "vim"):
        wrapper = shim_dir / command
        assert wrapper.exists()
        content = wrapper.read_text(encoding="utf-8")
        assert "--cmd 'set t_RV= t_u7= t_RF= t_RB= t_RK='" in content
        assert f"real_command=$(command -v {command} 2>/dev/null)" in content


def test_terminal_shims_skip_vim_wrappers_when_compatibility_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider = LocalPtyTerminalProvider()
    provider.vim_compatibility = False

    def fake_mkdtemp(prefix: str) -> str:
        path = tmp_path / prefix.rstrip("-")
        path.mkdir()
        return str(path)

    monkeypatch.setattr("backend.app.providers.terminal.local_pty.tempfile.mkdtemp", fake_mkdtemp)

    shim_dir = provider._ensure_transfer_shims()

    assert (shim_dir / "rz").exists()
    assert (shim_dir / "sz").exists()
    assert not (shim_dir / "vi").exists()
    assert not (shim_dir / "vim").exists()


def test_terminal_session_sync_cwd_validates_workspace(tmp_path: Path) -> None:
    provider = FakeTerminalProvider()
    provider.start(str(tmp_path), 24, 80)
    created_at = utc_now()
    session = TerminalSession(
        session_id="term_test",
        client_id=CLIENT_A,
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


def test_terminal_session_extracts_cwd_marker_without_echo(tmp_path: Path) -> None:
    provider = FakeTerminalProvider()
    provider.start(str(tmp_path), 24, 80)
    created_at = utc_now()
    session = TerminalSession(
        session_id="term_test",
        client_id=CLIENT_A,
        provider=provider,
        cwd=str(tmp_path),
        created_at=created_at,
        last_active_at=created_at,
        security=WorkspaceSecurity(tmp_path),
        allow_sync_cwd=True,
    )
    subdir = tmp_path / "calc"
    subdir.mkdir()

    provider.writes.clear()
    provider.read = lambda size=4096: f"before\x1b]633;P;Cwd={subdir}\x07after"  # type: ignore[method-assign]

    assert session.read() == "beforeafter"
    assert session.cwd == str(subdir.resolve())
    assert session.consume_cwd_update() == str(subdir.resolve())
    assert session.consume_cwd_update() is None


def test_terminal_manager_enforces_session_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(
        workspace=WorkspaceConfig(root=tmp_path),
        terminal=TerminalConfig(max_sessions=1, default_rows=33, default_cols=101),
    )
    manager = TerminalManager()

    session = manager.create_session(settings, CLIENT_A, None, None, None, None)

    assert session.cwd == str(tmp_path.resolve())
    assert session.provider.rows == 33
    assert session.provider.cols == 101

    with pytest.raises(AppError) as exc:
        manager.create_session(settings, CLIENT_A, None, None, None, None)

    assert exc.value.code == "TERMINAL_LIMIT_REACHED"
    other_session = manager.create_session(settings, CLIENT_B, None, None, None, None)
    assert other_session.client_id == CLIENT_B

    manager.close_session(session.session_id, CLIENT_A)
    manager.close_session(other_session.session_id, CLIENT_B)


def test_terminal_manager_passes_vim_compatibility_to_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(workspace=WorkspaceConfig(root=tmp_path))
    manager = TerminalManager()

    session = manager.create_session(settings, CLIENT_A, None, None, None, None, vim_compatibility=False)

    assert getattr(session.provider, "vim_compatibility") is False

    manager.close_session(session.session_id, CLIENT_A)


def test_terminal_manager_releases_session_after_client_disconnect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(workspace=WorkspaceConfig(root=tmp_path))
    manager = TerminalManager()
    session = manager.create_session(settings, CLIENT_A, None, None, None, None)

    attached = manager.attach_client(session.session_id, CLIENT_A)
    manager.detach_client(session.session_id, CLIENT_A)

    assert attached.clients == 0
    assert attached.is_alive() is False
    assert manager.list_sessions(CLIENT_A) == []


def test_terminal_manager_scopes_sessions_to_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    settings = Settings(workspace=WorkspaceConfig(root=tmp_path))
    manager = TerminalManager()

    session_a = manager.create_session(settings, CLIENT_A, None, None, None, None)
    session_b = manager.create_session(settings, CLIENT_B, None, None, None, None)

    assert [item.session_id for item in manager.list_sessions(CLIENT_A)] == [session_a.session_id]
    assert [item.session_id for item in manager.list_sessions(CLIENT_B)] == [session_b.session_id]

    with pytest.raises(AppError) as exc:
        manager.close_session(session_b.session_id, CLIENT_A)

    assert exc.value.code == "TERMINAL_SESSION_NOT_FOUND"
    assert session_b.is_alive() is True

    with pytest.raises(AppError) as exc:
        manager.attach_client(session_b.session_id, CLIENT_A)

    assert exc.value.code == "TERMINAL_SESSION_NOT_FOUND"

    manager.close_session(session_a.session_id, CLIENT_A)
    manager.close_session(session_b.session_id, CLIENT_B)


def test_terminal_sessions_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("backend.app.services.terminal_service.LocalPtyTerminalProvider", FakeTerminalProvider)
    terminal_manager.sessions.clear()
    settings = Settings(workspace=WorkspaceConfig(root=tmp_path))
    client = TestClient(create_app(settings))

    missing_client = client.get("/api/terminal/sessions")
    assert missing_client.status_code == 400
    assert missing_client.json()["error"]["code"] == "CLIENT_ID_REQUIRED"

    created = client.post(
        "/api/terminal/sessions",
        headers=CLIENT_A_HEADERS,
        json={"cwd": str(tmp_path), "rows": 20, "cols": 80, "vim_compatibility": False},
    )

    assert created.status_code == 200
    session_id = created.json()["session_id"]
    assert getattr(terminal_manager.sessions[session_id].provider, "vim_compatibility") is False

    listed = client.get("/api/terminal/sessions", headers=CLIENT_A_HEADERS)
    assert listed.status_code == 200
    assert any(item["session_id"] == session_id for item in listed.json()["items"])

    other_listed = client.get("/api/terminal/sessions", headers=CLIENT_B_HEADERS)
    assert other_listed.status_code == 200
    assert other_listed.json()["items"] == []

    wrong_client_close = client.delete(f"/api/terminal/sessions/{session_id}", headers=CLIENT_B_HEADERS)
    assert wrong_client_close.status_code == 404

    closed = client.delete(f"/api/terminal/sessions/{session_id}", headers=CLIENT_A_HEADERS)
    assert closed.status_code == 200
    assert closed.json()["success"] is True
