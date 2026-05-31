from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.core.security import WorkspaceSecurity
from backend.app.providers.terminal.base import TerminalProvider
from backend.app.services.terminal_service import TerminalSession


class DummyTerminalProvider(TerminalProvider):
    def __init__(self, chunks: list[str], ack_root: Path | None = None) -> None:
        self.chunks = chunks
        self.control_writes: list[str] = []
        self.ack_root = ack_root

    @property
    def shell(self) -> str:
        return "dummy"

    def start(self, cwd: str, rows: int, cols: int, shell: str | None = None) -> None:
        return None

    def write(self, data: str) -> None:
        self.control_writes.append(data)

    def read(self, size: int = 4096) -> str:
        if not self.chunks:
            return ""
        return self.chunks.pop(0)

    def resize(self, rows: int, cols: int) -> None:
        return None

    def terminate(self) -> None:
        return None

    def is_alive(self) -> bool:
        return True

    def resolve_transfer_ack_path(self, raw_path: str) -> Path | None:
        if self.ack_root is None:
            return None
        path = Path(raw_path).resolve()
        root = self.ack_root.resolve()
        if path == root or root in path.parents:
            return path
        return None


def make_session(root: Path, chunks: list[str], ack_root: Path | None = None) -> TerminalSession:
    now = datetime.now(timezone.utc)
    return TerminalSession(
        session_id="term_test",
        client_id="client_test",
        provider=DummyTerminalProvider(chunks, ack_root),
        cwd=str(root),
        created_at=now,
        last_active_at=now,
        security=WorkspaceSecurity(root),
        allow_sync_cwd=True,
    )


def transfer_marker(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"\x1b]777;chemssh-transfer;{encoded}\x07"


def test_terminal_transfer_marker_is_hidden_and_queues_rz_upload(tmp_path: Path) -> None:
    session = make_session(
        tmp_path,
        [f"before{transfer_marker({'direction': 'upload', 'argv': ['rz', '-y'], 'cwd': str(tmp_path)})}after"],
    )

    output = session.read()
    transfers = session.consume_transfer_requests()

    assert output == "beforeafter"
    assert len(transfers) == 1
    assert transfers[0].direction == "upload"
    assert transfers[0].cwd == str(tmp_path)
    assert transfers[0].argv == ["rz", "-y"]


def test_terminal_transfer_marker_resolves_sz_paths(tmp_path: Path) -> None:
    sample = tmp_path / "result.out"
    sample.write_text("ok\n", encoding="utf-8")
    session = make_session(
        tmp_path,
        [transfer_marker({"direction": "download", "argv": ["sz", "result.out"], "cwd": str(tmp_path)})],
    )

    assert session.read() == ""
    [transfer] = session.consume_transfer_requests()

    assert transfer.direction == "download"
    assert transfer.paths == [str(sample)]
    assert transfer.error is None


def test_terminal_transfer_marker_strips_crlf_from_sz_arguments(tmp_path: Path) -> None:
    sample = tmp_path / "CONTCAR"
    sample.write_text("ok\n", encoding="utf-8")
    session = make_session(
        tmp_path,
        [transfer_marker({"direction": "download", "argv": ["sz", "-Oq", "CONTCAR\r"], "cwd": f"{tmp_path}\r"})],
    )

    assert session.read() == ""
    [transfer] = session.consume_transfer_requests()

    assert transfer.paths == [str(sample)]
    assert transfer.error is None


def test_terminal_transfer_result_writes_ack_before_script_continues(tmp_path: Path) -> None:
    ack_root = tmp_path / "shim" / "acks"
    ack_path = ack_root / "transfer.json"
    session = make_session(
        tmp_path,
        [transfer_marker({"direction": "upload", "argv": ["rz"], "cwd": str(tmp_path), "ack_path": str(ack_path)})],
        ack_root=ack_root,
    )

    assert session.read() == ""
    [transfer] = session.consume_transfer_requests()

    message = session.format_transfer_result(transfer.transfer_id, True, "done")

    assert "complete" in message
    assert json.loads(ack_path.read_text(encoding="utf-8")) == {"success": True, "message": "done"}


def test_terminal_transfer_marker_blocks_sz_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope\n", encoding="utf-8")
    session = make_session(
        tmp_path,
        [transfer_marker({"direction": "download", "argv": ["sz", str(outside)], "cwd": str(tmp_path)})],
    )

    assert session.read() == ""
    [transfer] = session.consume_transfer_requests()

    assert transfer.direction == "download"
    assert transfer.paths == []
    assert transfer.error


def test_terminal_transfer_marker_can_span_reads(tmp_path: Path) -> None:
    marker = transfer_marker({"direction": "upload", "argv": ["rz"], "cwd": str(tmp_path)})
    session = make_session(tmp_path, [marker[:12], marker[12:]])

    assert session.read() == ""
    assert session.consume_transfer_requests() == []
    assert session.read() == ""

    assert len(session.consume_transfer_requests()) == 1


def test_native_rz_zmodem_signature_is_intercepted_as_upload(tmp_path: Path) -> None:
    session = make_session(tmp_path, ["rz waiting to receive.**B0100"])

    output = session.read()
    [transfer] = session.consume_transfer_requests()

    assert "native rz/ZMODEM was intercepted" in output
    assert transfer.direction == "upload"
    assert transfer.argv == ["rz"]
    assert "\x03" in session.provider.control_writes


def test_native_sz_zmodem_signature_is_intercepted_without_paths(tmp_path: Path) -> None:
    session = make_session(tmp_path, ["**B00000000000000"])

    output = session.read()

    assert "native sz/ZMODEM was intercepted" in output
    assert session.consume_transfer_requests() == []
    assert "\x03" in session.provider.control_writes
