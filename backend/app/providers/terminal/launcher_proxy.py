from __future__ import annotations

import ipaddress
import json
import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

BRIDGE_VERSION = 1
BRIDGE_DIR_NAME = ".chemssh-launcher"
CONNECT_TIMEOUT_SECONDS = 0.5
MAX_BRIDGE_BYTES = 64 * 1024

_PROXY_URL_KEYS = ("http_proxy", "https_proxy", "all_proxy")
_NO_PROXY_KEYS = ("no_proxy",)
# Exported so terminal providers can drop inherited proxy variables before
# applying the bridge values.
PROXY_ENV_KEYS = frozenset(
    key
    for base in _PROXY_URL_KEYS + _NO_PROXY_KEYS
    for key in (base, base.upper())
)


@dataclass(frozen=True)
class LauncherProxy:
    proxy_url: str
    env: dict[str, str]


def bridge_path(port: int, home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home)
    return base / BRIDGE_DIR_NAME / f"terminal-proxy-{int(port)}.json"


def load_launcher_proxy(
    port: int,
    *,
    home: Path | None = None,
    timeout: float = CONNECT_TIMEOUT_SECONDS,
) -> LauncherProxy | None:
    """Load the proxy environment published by the launcher for this port.

    The launcher writes the bridge file while its session runs and removes it on
    stop. A missing, stale, or invalid file returns None so terminals keep
    working without the proxy.
    """
    path = bridge_path(port, home)
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("Ignoring launcher proxy bridge %s: %s", path, exc)
        return None
    if size > MAX_BRIDGE_BYTES:
        logger.warning("Ignoring launcher proxy bridge %s: %d bytes exceeds the %d byte limit", path, size, MAX_BRIDGE_BYTES)
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring launcher proxy bridge %s: %s", path, exc)
        return None
    if not isinstance(raw, dict) or raw.get("version") != BRIDGE_VERSION:
        logger.info("Ignoring launcher proxy bridge %s: unsupported payload version", path)
        return None

    parsed = _parse_loopback_proxy(raw.get("proxy_url"))
    if parsed is None:
        logger.info("Ignoring launcher proxy bridge %s: proxy_url is not a bare loopback http URL", path)
        return None
    proxy_url, host, proxy_port = parsed
    if not _reachable(host, proxy_port, timeout):
        logger.info("Launcher proxy bridge %s is stale: %s is unreachable", path, proxy_url)
        return None

    no_proxy_value = raw.get("no_proxy")
    no_proxy = no_proxy_value.strip() if isinstance(no_proxy_value, str) and "\x00" not in no_proxy_value else ""
    return LauncherProxy(proxy_url=proxy_url, env=_proxy_env(raw.get("env"), proxy_url, no_proxy))


def _parse_loopback_proxy(value: object) -> tuple[str, str, int] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    proxy_url = value.strip()
    try:
        parts = urlsplit(proxy_url)
        port = parts.port if parts.port is not None else 80
    except ValueError:
        return None
    if parts.scheme != "http" or not parts.hostname:
        return None
    # The launcher writes a bare http://<loopback>:<port> URL. Credentials would
    # end up in logs and terminal environments, and a path or query never makes
    # sense for a proxy endpoint, so reject anything that is not that shape.
    if parts.username or parts.password or parts.path or parts.query or parts.fragment:
        return None
    if not 1 <= port <= 65535 or not _is_loopback(parts.hostname):
        return None
    return proxy_url, parts.hostname, port


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.strip().lower() == "localhost"


def _reachable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _proxy_env(raw: object, proxy_url: str, no_proxy: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in PROXY_ENV_KEYS or not isinstance(value, str) or "\x00" in value:
                continue
            if key.lower() in _PROXY_URL_KEYS and value.strip() != proxy_url:
                continue
            env[key] = value

    for key in _PROXY_URL_KEYS:
        env.setdefault(key, proxy_url)
        env.setdefault(key.upper(), proxy_url)
    if no_proxy:
        env.setdefault("no_proxy", no_proxy)
        env.setdefault("NO_PROXY", no_proxy)
    return env
