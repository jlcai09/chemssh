from __future__ import annotations

import argparse
import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import uvicorn

from backend.app.core.config import load_settings
from backend.app.main import create_app


@dataclass(frozen=True)
class ExistingChemwebServer:
    url: str
    project_version: str | None
    workspace_root: str | None


@dataclass(frozen=True)
class PortProbeResult:
    occupied: bool
    chemweb: ExistingChemwebServer | None = None
    detail: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chemweb")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--workspace-root", help="Workspace root directory")
    parser.add_argument("--host", help="Bind host, defaults to config server.host")
    parser.add_argument("--port", type=int, help="Bind port, defaults to config server.port")
    parser.add_argument(
        "--reuse-existing",
        choices=["auto", "never", "any-chemweb"],
        default="auto",
        help=(
            "How to handle an occupied port before startup. "
            "'auto' reuses an existing Chemweb server with the same workspace, "
            "'any-chemweb' reuses any Chemweb server on that port, and 'never' fails."
        ),
    )
    parser.add_argument(
        "--check-port",
        action="store_true",
        help="Check the configured host and port, then exit without starting the server.",
    )
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")
    parser.add_argument("--log-level", default="info", help="uvicorn log level")
    return parser


def _probe_host(host: str) -> str:
    if host in {"0.0.0.0", ""}:
        return "127.0.0.1"
    if host == "::":
        return "::1"
    return host


def _host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _server_url(host: str, port: int) -> str:
    client_host = _probe_host(host)
    return f"http://{_host_for_url(client_host)}:{port}"


def _same_workspace(left: str | None, right: Path) -> bool:
    if not left:
        return False
    try:
        return Path(left).expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return False


def _probe_existing_server(host: str, port: int, *, timeout: float = 1.0) -> PortProbeResult:
    client_host = _probe_host(host)
    try:
        with socket.create_connection((client_host, port), timeout=timeout):
            pass
    except OSError:
        return PortProbeResult(occupied=False)

    base_url = _server_url(host, port)
    identity_url = f"{base_url}/api/system/identity"
    request = Request(identity_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return PortProbeResult(occupied=True, detail=f"HTTP {exc.code} from {identity_url}")
    except (OSError, URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return PortProbeResult(occupied=True, detail=str(exc))

    if not isinstance(payload, dict) or payload.get("app") != "chemweb":
        return PortProbeResult(occupied=True, detail=f"{identity_url} did not return a Chemweb identity")

    return PortProbeResult(
        occupied=True,
        chemweb=ExistingChemwebServer(
            url=base_url,
            project_version=payload.get("project_version") if isinstance(payload.get("project_version"), str) else None,
            workspace_root=payload.get("workspace_root") if isinstance(payload.get("workspace_root"), str) else None,
        ),
    )


def _handle_existing_server(args: argparse.Namespace, host: str, port: int, workspace_root: Path) -> bool:
    probe = _probe_existing_server(host, port)
    if not probe.occupied:
        return False

    if args.reuse_existing == "never":
        raise RuntimeError(f"Port {port} on {host} is already occupied.")

    if probe.chemweb is None:
        message = f"Port {port} on {host} is occupied, but it is not a reusable Chemweb server."
        if probe.detail:
            message = f"{message} Detail: {probe.detail}"
        raise RuntimeError(message)

    existing = probe.chemweb
    if args.reuse_existing == "auto" and not _same_workspace(existing.workspace_root, workspace_root):
        raise RuntimeError(
            "Port {port} on {host} is already used by Chemweb, but with a different workspace: "
            "{existing_workspace}. Current workspace: {current_workspace}. "
            "Use --reuse-existing any-chemweb only if you intentionally want to connect to it.".format(
                port=port,
                host=host,
                existing_workspace=existing.workspace_root or "<unknown>",
                current_workspace=workspace_root,
            )
        )

    print(f"Chemweb is already running at {existing.url}; reusing the existing server.")
    if existing.workspace_root:
        print(f"Workspace: {existing.workspace_root}")
    return True


def _check_port_only(args: argparse.Namespace, host: str, port: int, workspace_root: Path) -> int:
    probe = _probe_existing_server(host, port)
    if not probe.occupied:
        print(f"Port {port} on {host} is available.")
        return 0

    if args.reuse_existing == "never":
        print(f"Port {port} on {host} is occupied and --reuse-existing is never.", file=sys.stderr)
        return 1

    if probe.chemweb is None:
        message = f"Port {port} on {host} is occupied, but it is not a reusable Chemweb server."
        if probe.detail:
            message = f"{message} Detail: {probe.detail}"
        print(message, file=sys.stderr)
        return 1

    existing = probe.chemweb
    if args.reuse_existing == "auto" and not _same_workspace(existing.workspace_root, workspace_root):
        print(
            "Port {port} on {host} is used by Chemweb with a different workspace: "
            "{existing_workspace}. Current workspace: {current_workspace}.".format(
                port=port,
                host=host,
                existing_workspace=existing.workspace_root or "<unknown>",
                current_workspace=workspace_root,
            ),
            file=sys.stderr,
        )
        return 1

    print(f"Port {port} on {host} is used by a reusable Chemweb server.")
    print(f"URL: {existing.url}")
    if existing.workspace_root:
        print(f"Workspace: {existing.workspace_root}")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config, workspace_root=args.workspace_root)
    host = args.host or settings.server.host
    port = args.port or settings.server.port

    if args.check_port:
        raise SystemExit(_check_port_only(args, host, port, settings.workspace.root))

    try:
        if _handle_existing_server(args, host, port, settings.workspace.root):
            return
    except RuntimeError as exc:
        print(f"chemweb: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.reload:
        uvicorn.run(
            "backend.app.main:app",
            host=host,
            port=port,
            reload=True,
            log_level=args.log_level,
        )
        return

    server: uvicorn.Server | None = None

    def request_shutdown() -> None:
        if server is not None:
            server.should_exit = True

    app = create_app(settings, idle_shutdown_callback=request_shutdown)
    config = uvicorn.Config(app, host=host, port=port, log_level=args.log_level)
    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()
