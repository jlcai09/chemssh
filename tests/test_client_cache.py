from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import ClientCacheConfig, Settings, WorkspaceConfig
from backend.app.main import create_app
from backend.app.services.client_cache_service import ClientCacheService


CLIENT_ID = "client_test"
HEADERS = {"X-ChemSSH-Client-Id": CLIENT_ID}


def make_client(tmp_path: Path, *, enabled: bool = True, max_file_size_kb: int = 512) -> TestClient:
    settings = Settings(
        workspace=WorkspaceConfig(root=tmp_path / "workspace"),
        client_cache=ClientCacheConfig(
            enabled=enabled,
            directory=tmp_path / "cache",
            max_file_size_kb=max_file_size_kb,
        ),
    )
    return TestClient(create_app(settings))


def test_client_cache_requires_client_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/client-cache")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CLIENT_ID_REQUIRED"


def test_client_cache_rejects_invalid_client_id(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/client-cache", headers={"X-ChemSSH-Client-Id": "../bad"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CLIENT_ID"


def test_client_cache_first_read_creates_meta(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/client-cache", headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == CLIENT_ID
    assert data["preferences"] == {"version": 1}
    assert data["boards"] == {"version": 1, "activeBoardId": None, "boards": []}
    assert (tmp_path / "cache" / CLIENT_ID / "meta.json").exists()


def test_client_cache_saves_preferences_and_boards(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    preferences = {"version": 1, "logs": {"tailLines": 80}}
    boards = {
        "version": 1,
        "activeBoardId": "board_1",
        "boards": [{"id": "board_1", "name": "Main", "windows": []}],
    }

    pref_response = client.put("/api/client-cache/preferences", headers=HEADERS, json=preferences)
    board_response = client.put("/api/client-cache/boards", headers=HEADERS, json=boards)
    read_response = client.get("/api/client-cache", headers=HEADERS)

    assert pref_response.status_code == 200
    assert board_response.status_code == 200
    assert read_response.status_code == 200
    data = read_response.json()
    assert data["preferences"] == preferences
    assert data["boards"] == boards


def test_client_cache_scopes_preferences_and_boards(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    local_headers = {**HEADERS, "X-ChemSSH-Cache-Scope": "scope_local"}
    remote_headers = {**HEADERS, "X-ChemSSH-Cache-Scope": "scope_remote"}
    local_preferences = {"version": 1, "workspace": {"currentPath": "D:\\Git\\chemssh"}}
    remote_preferences = {"version": 1, "workspace": {"currentPath": "/data/user/chemssh"}}

    local_response = client.put("/api/client-cache/preferences", headers=local_headers, json=local_preferences)
    remote_response = client.put("/api/client-cache/preferences", headers=remote_headers, json=remote_preferences)
    local_read = client.get("/api/client-cache", headers=local_headers)
    remote_read = client.get("/api/client-cache", headers=remote_headers)

    assert local_response.status_code == 200
    assert remote_response.status_code == 200
    assert local_read.json()["preferences"] == local_preferences
    assert remote_read.json()["preferences"] == remote_preferences
    assert (tmp_path / "cache" / CLIENT_ID / "scopes" / "scope_local" / "preferences.json").exists()
    assert (tmp_path / "cache" / CLIENT_ID / "scopes" / "scope_remote" / "preferences.json").exists()


def test_client_cache_rejects_invalid_scope(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/client-cache", headers={**HEADERS, "X-ChemSSH-Cache-Scope": "../bad"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CLIENT_CACHE_SCOPE"


def test_client_cache_rejects_large_payload(tmp_path: Path) -> None:
    client = make_client(tmp_path, max_file_size_kb=16)

    response = client.put("/api/client-cache/preferences", headers=HEADERS, json={"value": "x" * (20 * 1024)})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "CLIENT_CACHE_TOO_LARGE"


def test_client_cache_disabled(tmp_path: Path) -> None:
    client = make_client(tmp_path, enabled=False)

    response = client.get("/api/client-cache", headers=HEADERS)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLIENT_CACHE_DISABLED"


def test_client_cache_heartbeat_updates_last_seen(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/api/client-cache/heartbeat", headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["client_id"] == CLIENT_ID
    meta = json.loads((tmp_path / "cache" / CLIENT_ID / "meta.json").read_text(encoding="utf-8"))
    assert meta["last_seen_at"] == response.json()["last_seen_at"]


def test_client_cache_clear_removes_current_client_only(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    other_dir = tmp_path / "cache" / "client_other"
    other_dir.mkdir(parents=True)
    (other_dir / "preferences.json").write_text("{}", encoding="utf-8")
    response = client.put("/api/client-cache/preferences", headers=HEADERS, json={"version": 1})
    assert response.status_code == 200

    clear = client.delete("/api/client-cache", headers=HEADERS)

    assert clear.status_code == 200
    assert clear.json()["removed"] is True
    assert not (tmp_path / "cache" / CLIENT_ID).exists()
    assert other_dir.exists()


def test_client_cache_cleanup_removes_stale_clients(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    stale_dir = cache_root / "client_stale"
    fresh_dir = cache_root / "client_fresh"
    stale_dir.mkdir(parents=True)
    fresh_dir.mkdir(parents=True)
    now = datetime(2026, 6, 5, tzinfo=timezone.utc)
    (stale_dir / "meta.json").write_text(
        json.dumps({"last_seen_at": (now - timedelta(days=20)).isoformat()}),
        encoding="utf-8",
    )
    (fresh_dir / "meta.json").write_text(
        json.dumps({"last_seen_at": (now - timedelta(days=2)).isoformat()}),
        encoding="utf-8",
    )
    settings = Settings(client_cache=ClientCacheConfig(directory=cache_root, cleanup_offline_days=14))
    service = ClientCacheService(settings)

    result = service.cleanup_stale_clients(now)

    assert result.scanned == 2
    assert result.removed == 1
    assert not stale_dir.exists()
    assert fresh_dir.exists()
