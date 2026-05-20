from io import BytesIO
from pathlib import Path
import subprocess
from zipfile import ZipFile

from fastapi.testclient import TestClient

from backend.app import __version__
from backend.app.core.config import BrotliConfig, CompressionConfig, SchedulerConfig, Settings, WorkspaceConfig
from backend.app.main import create_app
from backend.app.providers.scheduler import pbs as pbs_provider
from backend.app.providers.scheduler import slurm as slurm_provider


def make_client(root: Path, scheduler: str = "slurm") -> TestClient:
    settings = Settings(workspace=WorkspaceConfig(root=root), scheduler=SchedulerConfig(type=scheduler))
    return TestClient(create_app(settings))


def make_client_with_compression(root: Path, enabled: bool = True, level: int = 1) -> TestClient:
    settings = Settings(
        workspace=WorkspaceConfig(root=root),
        compression=CompressionConfig(brotli=BrotliConfig(enabled=enabled, level=level)),
    )
    return TestClient(create_app(settings))


def make_client_with_read_limit(root: Path, max_read_size_mb: int) -> TestClient:
    settings = Settings(workspace=WorkspaceConfig(root=root, max_read_size_mb=max_read_size_mb))
    return TestClient(create_app(settings))


def test_openapi_uses_project_version(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["version"] == __version__


def test_system_info_and_file_roundtrip(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "sample.xyz"
    sample.write_text("1\nwater\nH 0 0 0\n", encoding="utf-8")

    system = client.get("/api/system/info")
    assert system.status_code == 200
    assert system.json()["project_version"] == __version__
    assert system.json()["workspace_root"] == str(tmp_path.resolve())

    listing = client.get("/api/files/list")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["preview_type"] == "structure"

    read = client.get("/api/files/read", params={"path": str(sample)})
    assert read.status_code == 200
    assert read.json()["format"] == "xyz"

    write = client.post(
        "/api/files/write",
        json={"path": str(tmp_path / "input.inp"), "content": "alpha=1\n"},
    )
    assert write.status_code == 200
    assert (tmp_path / "input.inp").read_text(encoding="utf-8") == "alpha=1\n"


def test_file_read_can_force_large_preview(tmp_path: Path) -> None:
    client = make_client_with_read_limit(tmp_path, max_read_size_mb=0)
    sample = tmp_path / "large.txt"
    sample.write_bytes(b"large file\n")

    blocked = client.get("/api/files/read", params={"path": str(sample)})
    forced = client.get("/api/files/read", params={"path": str(sample), "force": True})

    assert blocked.status_code == 413
    assert blocked.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert forced.status_code == 200
    assert forced.json()["content"] == "large file\n"


def test_brotli_compresses_json_when_client_accepts_br(tmp_path: Path) -> None:
    client = make_client_with_compression(tmp_path)
    response = client.get("/api/system/info", headers={"Accept-Encoding": "br"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "br"
    assert "accept-encoding" in response.headers["vary"].lower()
    assert response.json()["workspace_root"] == str(tmp_path.resolve())


def test_brotli_can_be_disabled(tmp_path: Path) -> None:
    client = make_client_with_compression(tmp_path, enabled=False)
    response = client.get("/api/system/info", headers={"Accept-Encoding": "br"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_brotli_respects_zero_quality(tmp_path: Path) -> None:
    client = make_client_with_compression(tmp_path)
    response = client.get("/api/system/info", headers={"Accept-Encoding": "br;q=0, *;q=1"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_files_api_blocks_path_traversal(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/files/list", params={"path": str(tmp_path / "..")})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_PATH"


def test_tail_defaults_and_cap(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "payload.bin"
    sample.write_text("".join(f"line {i}\n" for i in range(1, 151)), encoding="utf-8")

    default_tail = client.get("/api/files/tail", params={"path": str(sample)})
    assert default_tail.status_code == 200
    assert default_tail.json()["lines"] == 20
    assert default_tail.json()["content"].splitlines() == [f"line {i}" for i in range(131, 151)]

    capped_tail = client.get("/api/files/tail", params={"path": str(sample), "lines": 500})
    assert capped_tail.status_code == 200
    assert capped_tail.json()["lines"] == 100
    assert capped_tail.json()["content"].splitlines() == [f"line {i}" for i in range(51, 151)]


def test_download_archive_contains_selected_paths(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "sample.txt"
    folder = tmp_path / "folder"
    nested = folder / "nested.txt"
    folder.mkdir()
    sample.write_text("sample\n", encoding="utf-8")
    nested.write_text("nested\n", encoding="utf-8")

    response = client.post(
        "/api/files/download-archive",
        json={"paths": [str(sample), str(folder)]},
    )

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "sample.txt" in names
        assert "folder/" in names
        assert "folder/nested.txt" in names


def test_submit_job_uses_requested_queue_command(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    script = tmp_path / "vasp.script"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_which(command: str) -> str:
        return f"/usr/bin/{command}"

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(command, 0, stdout="12345.server\n", stderr="")

    monkeypatch.setattr(slurm_provider.shutil, "which", fake_which)
    monkeypatch.setattr(slurm_provider.subprocess, "run", fake_run)

    response = client.post(
        "/api/jobs/submit",
        json={"workdir": str(tmp_path), "script": "vasp.script", "command": "qsub"},
    )

    assert response.status_code == 200
    assert captured["command"] == ["qsub", "vasp.script"]
    assert captured["cwd"] == str(tmp_path.resolve())
    assert response.json()["scheduler"] == "qsub"
    assert response.json()["job_id"] == "12345.server"


def test_pbs_queue_actions_use_pbs_commands(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path, scheduler="pbs")
    captured: list[list[str]] = []

    def fake_which(command: str) -> str:
        return f"/usr/bin/{command}"

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(pbs_provider.shutil, "which", fake_which)
    monkeypatch.setattr(pbs_provider.subprocess, "run", fake_run)

    hold = client.post("/api/queue/action", json={"job_id": "123.server", "action": "hold"})
    release = client.post("/api/queue/action", json={"job_id": "123.server", "action": "release"})
    cancel = client.post("/api/queue/action", json={"job_id": "123.server", "action": "cancel"})

    assert hold.status_code == 200
    assert release.status_code == 200
    assert cancel.status_code == 200
    assert captured == [["qhold", "123.server"], ["qrls", "123.server"], ["qdel", "123.server"]]
