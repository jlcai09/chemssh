from io import BytesIO
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile

from fastapi.testclient import TestClient

from backend.app import __version__
from backend.app.core.config import BrotliConfig, CompressionConfig, PluginsConfig, SchedulerConfig, Settings, WorkspaceConfig
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

    identity = client.get("/api/system/identity")
    assert identity.status_code == 200
    assert identity.json()["app"] == "chemweb"
    assert identity.json()["project_version"] == __version__
    assert identity.json()["workspace_root"] == str(tmp_path.resolve())

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


def test_plugins_can_be_listed_activated_and_served(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "sample.log"
    sample.write_text("not a quantum chemistry output\n", encoding="utf-8")

    listing = client.get("/api/plugins")
    assert listing.status_code == 200
    assert any(plugin["id"] == "cclib" for plugin in listing.json()["plugins"])

    dependencies = client.get("/api/plugins/cclib/dependencies")
    assert dependencies.status_code == 200
    assert dependencies.json()["python"]["mode"] == "host"
    assert dependencies.json()["python"]["requirements"].endswith("plugins\\cclib\\backend\\requirements.txt") or dependencies.json()["python"]["requirements"].endswith("plugins/cclib/backend/requirements.txt")

    bad_external = client.post("/api/plugins/cclib/dependencies/external", json={"python": str(tmp_path / "missing-python")})
    assert bad_external.status_code == 404
    assert bad_external.json()["error"]["code"] == "PLUGIN_EXTERNAL_PYTHON_NOT_FOUND"

    activated = client.post("/api/plugins/cclib/activate")
    assert activated.status_code == 200
    assert activated.json()["api_base"] == "/api/plugins/cclib/api"

    asset = client.get("/api/plugins/cclib/assets")
    assert asset.status_code == 200
    assert b"cclib" in asset.content

    probe = client.post("/api/plugins/cclib/api/probe", json={"path": str(sample)})
    assert probe.status_code == 200
    assert probe.json()["handler"] == "cclib-output"


def test_plugin_get_routes_take_precedence_over_spa_fallback(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "dummy-get"
    backend_dir = plugin_dir / "backend"
    backend_dir.mkdir(parents=True)
    (plugin_dir / "chemweb-plugin.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "dummy-get",
                "name": "Dummy GET",
                "version": "0.1.0",
                "entry": {
                    "backend": {
                        "type": "python",
                        "module": "backend.plugin",
                        "factory": "create_plugin",
                    }
                },
                "panels": [{"id": "main", "title": "Dummy GET"}],
            }
        ),
        encoding="utf-8",
    )
    (backend_dir / "plugin.py").write_text(
        "\n".join(
            [
                "from fastapi import APIRouter",
                "",
                "class DummyPlugin:",
                "    def __init__(self, context):",
                "        self.router = APIRouter()",
                "        self.router.get('/hello')(self.hello)",
                "",
                "    def hello(self):",
                "        return {'ok': True}",
                "",
                "def create_plugin(context):",
                "    return DummyPlugin(context)",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(
        workspace=WorkspaceConfig(root=tmp_path),
        plugins=PluginsConfig(directories=[plugins_dir]),
    )
    client = TestClient(create_app(settings))

    activated = client.post("/api/plugins/dummy-get/activate")
    assert activated.status_code == 200

    response = client.get("/api/plugins/dummy-get/api/hello")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"ok": True}

    route_paths = [getattr(route, "path", None) for route in client.app.router.routes]
    if "/{full_path:path}" in route_paths:
        assert route_paths.index("/api/plugins/dummy-get/api/hello") < route_paths.index("/{full_path:path}")


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


def test_download_selection_get_archives_multiple_paths(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "sample.txt"
    folder = tmp_path / "folder"
    nested = folder / "nested.txt"
    folder.mkdir()
    sample.write_text("sample\n", encoding="utf-8")
    nested.write_text("nested\n", encoding="utf-8")

    response = client.get(
        "/api/files/download-selection",
        params=[("path", str(sample)), ("path", str(folder))],
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "sample.txt" in names
        assert "folder/" in names
        assert "folder/nested.txt" in names


def test_upload_accepts_relative_path_and_overwrites_nested_file(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    existing = tmp_path / "A" / "B.txt"
    keep = tmp_path / "A" / "C.txt"
    existing.parent.mkdir()
    existing.write_text("old\n", encoding="utf-8")
    keep.write_text("keep\n", encoding="utf-8")

    response = client.post(
        "/api/files/upload",
        data={"path": str(tmp_path), "relative_path": "A/B.txt"},
        files={"file": ("B.txt", b"new\n", "text/plain")},
    )

    assert response.status_code == 200
    assert existing.read_text(encoding="utf-8") == "new\n"
    assert keep.read_text(encoding="utf-8") == "keep\n"


def test_upload_relative_path_blocks_traversal(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/files/upload",
        data={"path": str(tmp_path), "relative_path": "../escape.txt"},
        files={"file": ("escape.txt", b"bad", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_NAME"


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


def test_slurm_queue_can_list_all_or_current_user(tmp_path: Path, monkeypatch) -> None:
    client = make_client(tmp_path)
    captured: list[list[str]] = []

    def fake_which(command: str) -> str:
        return f"/usr/bin/{command}"

    def fake_getuser() -> str:
        return "alice"

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        captured.append(command)
        payload = {
            "jobs": [
                {
                    "job_id": 101,
                    "name": "job",
                    "user_name": "bob",
                    "job_state": "RUNNING",
                    "partition": "debug",
                    "working_directory": str(tmp_path),
                }
            ]
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(slurm_provider.shutil, "which", fake_which)
    monkeypatch.setattr(slurm_provider.getpass, "getuser", fake_getuser)
    monkeypatch.setattr(slurm_provider.subprocess, "run", fake_run)

    all_jobs = client.get("/api/queue/list")
    current_user_jobs = client.get("/api/queue/list", params={"current_user_only": True})

    assert all_jobs.status_code == 200
    assert current_user_jobs.status_code == 200
    assert captured == [["squeue", "--json"], ["squeue", "-u", "alice", "--json"]]


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
