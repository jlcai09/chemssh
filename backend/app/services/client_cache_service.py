from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.core.paths import get_client_cache_root


DEFAULT_BOARDS: dict[str, Any] = {
    "version": 1,
    "activeBoardId": None,
    "boards": [],
}

DEFAULT_PREFERENCES: dict[str, Any] = {
    "version": 1,
}

CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


@dataclass
class CleanupResult:
    scanned: int = 0
    removed: int = 0
    failed: int = 0


class ClientCacheService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = get_client_cache_root(settings)
        self.max_bytes = settings.client_cache.max_file_size_kb * 1024

    def read_cache(self, client_id: str) -> dict[str, Any]:
        self._ensure_enabled()
        client_dir = self._client_dir(client_id)
        self._touch_meta(client_id, client_dir)
        return {
            "enabled": True,
            "client_id": client_id,
            "preferences": self._read_json(client_dir / "preferences.json", DEFAULT_PREFERENCES),
            "boards": self._read_json(client_dir / "boards.json", DEFAULT_BOARDS),
            "updated_at": self._iso_now(),
        }

    def write_preferences(self, client_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        self._ensure_enabled()
        client_dir = self._client_dir(client_id)
        self._write_json(client_dir / "preferences.json", preferences)
        self._touch_meta(client_id, client_dir, saved=True)
        return self.read_cache(client_id)

    def write_boards(self, client_id: str, boards: dict[str, Any]) -> dict[str, Any]:
        self._ensure_enabled()
        client_dir = self._client_dir(client_id)
        self._write_json(client_dir / "boards.json", boards)
        self._touch_meta(client_id, client_dir, saved=True)
        return self.read_cache(client_id)

    def heartbeat(self, client_id: str) -> dict[str, str]:
        self._ensure_enabled()
        client_dir = self._client_dir(client_id)
        meta = self._touch_meta(client_id, client_dir)
        return {"client_id": client_id, "last_seen_at": str(meta["last_seen_at"])}

    def clear_cache(self, client_id: str) -> dict[str, Any]:
        self._ensure_enabled()
        client_dir = self._client_dir_path(client_id)
        removed = False
        if client_dir.exists():
            shutil.rmtree(client_dir)
            removed = True
        return {
            "success": True,
            "client_id": client_id,
            "removed": removed,
        }

    def cleanup_stale_clients(self, now: datetime | None = None) -> CleanupResult:
        result = CleanupResult()
        if not self.settings.client_cache.enabled or not self.root.exists():
            return result

        current = now or datetime.now(timezone.utc)
        cutoff = current - timedelta(days=self.settings.client_cache.cleanup_offline_days)

        for client_dir in self.root.iterdir():
            if not client_dir.is_dir():
                continue
            try:
                self._validate_client_id(client_dir.name)
            except AppError:
                continue

            result.scanned += 1
            if not self._is_stale(client_dir, cutoff):
                continue

            try:
                shutil.rmtree(client_dir)
                result.removed += 1
            except OSError:
                result.failed += 1

        return result

    def _ensure_enabled(self) -> None:
        if not self.settings.client_cache.enabled:
            raise AppError("CLIENT_CACHE_DISABLED", "Client cache is disabled", 404)

    def _client_dir(self, client_id: str) -> Path:
        client_dir = self._client_dir_path(client_id)
        client_dir.mkdir(parents=True, exist_ok=True)
        return client_dir

    def _client_dir_path(self, client_id: str) -> Path:
        safe_client_id = self._validate_client_id(client_id)
        root = self.root.resolve()
        client_dir = (root / safe_client_id).resolve()
        if client_dir != root / safe_client_id:
            raise AppError("INVALID_CLIENT_ID", "Invalid client id", 400)
        if root not in client_dir.parents:
            raise AppError("INVALID_CLIENT_ID", "Invalid client id", 400)
        return client_dir

    def _touch_meta(self, client_id: str, client_dir: Path, *, saved: bool = False) -> dict[str, Any]:
        now = self._iso_now()
        meta_path = client_dir / "meta.json"
        meta = self._read_json(
            meta_path,
            {
                "client_id": client_id,
                "created_at": now,
                "last_seen_at": now,
                "last_saved_at": None,
            },
        )
        meta["client_id"] = client_id
        meta.setdefault("created_at", now)
        meta["last_seen_at"] = now
        if saved:
            meta["last_saved_at"] = now
        self._write_json(meta_path, meta)
        return meta

    def _read_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return dict(fallback)
        if path.stat().st_size > self.max_bytes:
            raise AppError("CLIENT_CACHE_TOO_LARGE", "Client cache file is too large", 413)
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return dict(fallback)
        return data if isinstance(data, dict) else dict(fallback)

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        encoded = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        if len(encoded.encode("utf-8")) > self.max_bytes:
            raise AppError("CLIENT_CACHE_TOO_LARGE", "Client cache payload is too large", 413)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.write("\n")
        tmp.replace(path)

    def _is_stale(self, client_dir: Path, cutoff: datetime) -> bool:
        meta = self._read_json(client_dir / "meta.json", {})
        raw_seen = meta.get("last_seen_at")
        seen_at = self._parse_datetime(raw_seen) if isinstance(raw_seen, str) else None
        if seen_at is None:
            seen_at = datetime.fromtimestamp(client_dir.stat().st_mtime, timezone.utc)
        return seen_at < cutoff

    @staticmethod
    def _validate_client_id(client_id: str) -> str:
        if not CLIENT_ID_RE.match(client_id):
            raise AppError("INVALID_CLIENT_ID", "Invalid client id", 400)
        return client_id

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
