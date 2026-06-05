from __future__ import annotations

from pathlib import Path

from backend.app.core.config import Settings


def get_install_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_client_cache_root(settings: Settings) -> Path:
    if settings.client_cache.directory is not None:
        return settings.client_cache.directory
    return get_install_root() / "cache"
