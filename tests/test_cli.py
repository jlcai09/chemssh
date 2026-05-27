from argparse import Namespace
from pathlib import Path

import pytest

from backend.app import cli


def _args(reuse_existing: str) -> Namespace:
    return Namespace(reuse_existing=reuse_existing)


def test_cli_reuses_existing_chemweb_with_same_workspace(tmp_path: Path, monkeypatch, capsys) -> None:
    existing = cli.ExistingChemwebServer(
        url="http://127.0.0.1:8888",
        project_version="0.2.0",
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=True, chemweb=existing),
    )

    reused = cli._handle_existing_server(_args("auto"), "127.0.0.1", 8888, tmp_path)

    assert reused is True
    assert "reusing the existing server" in capsys.readouterr().out


def test_cli_rejects_existing_chemweb_with_different_workspace(tmp_path: Path, monkeypatch) -> None:
    existing = cli.ExistingChemwebServer(
        url="http://127.0.0.1:8888",
        project_version="0.2.0",
        workspace_root=str(tmp_path / "other"),
    )
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=True, chemweb=existing),
    )

    with pytest.raises(RuntimeError, match="different workspace"):
        cli._handle_existing_server(_args("auto"), "127.0.0.1", 8888, tmp_path)


def test_cli_can_reuse_any_existing_chemweb(tmp_path: Path, monkeypatch) -> None:
    existing = cli.ExistingChemwebServer(
        url="http://127.0.0.1:8888",
        project_version="0.2.0",
        workspace_root=str(tmp_path / "other"),
    )
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=True, chemweb=existing),
    )

    reused = cli._handle_existing_server(_args("any-chemweb"), "127.0.0.1", 8888, tmp_path)

    assert reused is True


def test_cli_rejects_non_chemweb_port_occupant(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=True, detail="HTTP 404"),
    )

    with pytest.raises(RuntimeError, match="not a reusable Chemweb server"):
        cli._handle_existing_server(_args("auto"), "127.0.0.1", 8888, tmp_path)


def test_cli_does_not_reuse_when_port_is_free(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=False),
    )

    reused = cli._handle_existing_server(_args("auto"), "127.0.0.1", 8888, tmp_path)

    assert reused is False


def test_cli_check_port_reports_available_port(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=False),
    )

    exit_code = cli._check_port_only(_args("auto"), "127.0.0.1", 8888, tmp_path)

    assert exit_code == 0
    assert "available" in capsys.readouterr().out


def test_cli_check_port_reports_reusable_chemweb(tmp_path: Path, monkeypatch, capsys) -> None:
    existing = cli.ExistingChemwebServer(
        url="http://127.0.0.1:8888",
        project_version="0.2.0",
        workspace_root=str(tmp_path),
    )
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=True, chemweb=existing),
    )

    exit_code = cli._check_port_only(_args("auto"), "127.0.0.1", 8888, tmp_path)

    assert exit_code == 0
    assert "reusable Chemweb" in capsys.readouterr().out


def test_cli_check_port_rejects_unusable_port(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_probe_existing_server",
        lambda host, port: cli.PortProbeResult(occupied=True, detail="HTTP 404"),
    )

    exit_code = cli._check_port_only(_args("auto"), "127.0.0.1", 8888, tmp_path)

    assert exit_code == 1
    assert "not a reusable Chemweb server" in capsys.readouterr().err
