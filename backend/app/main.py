from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app import __version__
from backend.app.api import client_cache, files, jobs, plugins, queue, structures, system, terminal
from backend.app.core.config import Settings, get_settings, set_settings
from backend.app.core.errors import (
    AppError,
    app_error_handler,
    http_error_handler,
    validation_error_handler,
)
from backend.app.middleware.brotli import BrotliMiddleware
from backend.app.middleware.idle_shutdown import IdleShutdownManager, IdleShutdownMiddleware, ShutdownCallback
from backend.app.middleware.token_auth import TokenAuthMiddleware
from backend.app.middleware.structure_concurrency import StructureConcurrencyMiddleware
from backend.app.services.client_cache_service import ClientCacheService
from backend.app.services.plugin_service import PluginService


logger = logging.getLogger(__name__)


def _warm_structure_service() -> None:
    """Preload ase/scipy/numpy in the background after the server is up.

    Structure parsing is only needed once a file preview or scheduler stats
    request arrives. Importing it during startup adds seconds of cold-start
    delay, so the request path imports it lazily and this thread pays the cost
    off the critical path.
    """
    try:
        import backend.app.services.structure_service  # noqa: F401
    except Exception:
        logger.warning("Could not preload the structure service", exc_info=True)


def _build_lifespan(idle_shutdown: IdleShutdownManager):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await idle_shutdown.start()
        threading.Thread(
            target=_warm_structure_service,
            name="chemssh-structure-warmup",
            daemon=True,
        ).start()
        try:
            yield
        finally:
            await idle_shutdown.stop()

    return lifespan


def create_app(settings: Settings | None = None, *, idle_shutdown_callback: ShutdownCallback | None = None) -> FastAPI:
    if settings is not None:
        set_settings(settings)
    active_settings = get_settings()
    idle_shutdown = IdleShutdownManager(
        timeout_seconds=active_settings.server.idle_shutdown_seconds,
        shutdown_callback=idle_shutdown_callback,
    )

    app = FastAPI(
        title="chemssh",
        version=__version__,
        lifespan=_build_lifespan(idle_shutdown),
        description="计算催化与计算化学文件、作业和结构可视化工作台。",
    )
    app.state.settings = active_settings
    app.state.idle_shutdown = idle_shutdown
    app.state.plugin_service = PluginService(active_settings, app)
    app.state.client_cache_service = ClientCacheService(active_settings)
    app.state.client_cache_service.cleanup_stale_clients()

    app.add_middleware(
        BrotliMiddleware,
        enabled=active_settings.compression.brotli.enabled,
        quality=active_settings.compression.brotli.level,
    )
    app.add_middleware(StructureConcurrencyMiddleware)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    app.add_middleware(TokenAuthMiddleware, settings=active_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(IdleShutdownMiddleware, manager=idle_shutdown)

    app.include_router(system.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(structures.router, prefix="/api")
    app.include_router(queue.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(terminal.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    app.include_router(client_cache.router, prefix="/api")

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.exists():
        assets = frontend_dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(frontend_dist / "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            target = frontend_dist / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(frontend_dist / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def health() -> dict[str, str]:
            return {
                "name": "chemssh",
                "message": "Backend is running. Build the frontend to serve the web UI.",
            }

    return app


def __getattr__(name: str) -> FastAPI:
    """Build the ASGI app only when a server imports ``backend.app.main:app``.

    ``cli.main`` imports :func:`create_app` and passes explicit settings; an
    eager module-level app would be created and then thrown away, duplicating
    route registration and client-cache cleanup on every start.
    """
    if name != "app":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    app = create_app()
    globals()["app"] = app
    return app
