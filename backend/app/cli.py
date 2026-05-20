from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import uvicorn

from backend.app.core.config import load_settings
from backend.app.main import create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chemweb")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--workspace-root", help="Workspace root directory")
    parser.add_argument("--host", help="Bind host, defaults to config server.host")
    parser.add_argument("--port", type=int, help="Bind port, defaults to config server.port")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")
    parser.add_argument("--log-level", default="info", help="uvicorn log level")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config, workspace_root=args.workspace_root)
    host = args.host or settings.server.host
    port = args.port or settings.server.port

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
