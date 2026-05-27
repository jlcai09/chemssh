from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.services.plugin_service import PluginService


router = APIRouter(prefix="/plugins", tags=["plugins"])


class DependencyInstallRequest(BaseModel):
    mode: str | None = None
    venv: str | None = None


class ExternalPythonRequest(BaseModel):
    python: str


def _service(request: Request) -> PluginService:
    return request.app.state.plugin_service


@router.get("")
def list_plugins(request: Request) -> dict[str, object]:
    return {"plugins": _service(request).list_plugins()}


@router.post("/{plugin_id}/activate")
def activate_plugin(plugin_id: str, request: Request) -> dict[str, object]:
    return _service(request).activate(plugin_id)


@router.post("/{plugin_id}/deactivate")
def deactivate_plugin(plugin_id: str, request: Request) -> dict[str, object]:
    return _service(request).deactivate(plugin_id)


@router.get("/{plugin_id}/dependencies")
def plugin_dependency_status(plugin_id: str, request: Request) -> dict[str, object]:
    return _service(request).dependency_status(plugin_id)


@router.post("/{plugin_id}/dependencies/install")
def install_plugin_dependencies(
    plugin_id: str,
    payload: DependencyInstallRequest,
    request: Request,
) -> dict[str, object]:
    return _service(request).install_dependencies(plugin_id, mode=payload.mode, venv=payload.venv)


@router.post("/{plugin_id}/dependencies/external")
def configure_plugin_external_python(
    plugin_id: str,
    payload: ExternalPythonRequest,
    request: Request,
) -> dict[str, object]:
    return _service(request).configure_external_python(plugin_id, payload.python)


@router.get("/{plugin_id}/assets")
def plugin_index(plugin_id: str, request: Request) -> FileResponse:
    return FileResponse(_service(request).asset_path(plugin_id))


@router.get("/{plugin_id}/assets/{asset_path:path}")
def plugin_asset(plugin_id: str, asset_path: str, request: Request) -> FileResponse:
    return FileResponse(_service(request).asset_path(plugin_id, asset_path))
