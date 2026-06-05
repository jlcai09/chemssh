from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_client_cache_service, get_client_id_dependency
from backend.app.services.client_cache_service import ClientCacheService


router = APIRouter(prefix="/client-cache", tags=["client-cache"])


@router.get("")
def read_client_cache(
    client_id: str = Depends(get_client_id_dependency),
    service: ClientCacheService = Depends(get_client_cache_service),
) -> dict[str, Any]:
    return service.read_cache(client_id)


@router.put("/preferences")
def save_client_preferences(
    payload: dict[str, Any],
    client_id: str = Depends(get_client_id_dependency),
    service: ClientCacheService = Depends(get_client_cache_service),
) -> dict[str, Any]:
    return service.write_preferences(client_id, payload)


@router.put("/boards")
def save_client_boards(
    payload: dict[str, Any],
    client_id: str = Depends(get_client_id_dependency),
    service: ClientCacheService = Depends(get_client_cache_service),
) -> dict[str, Any]:
    return service.write_boards(client_id, payload)


@router.post("/heartbeat")
def heartbeat_client_cache(
    client_id: str = Depends(get_client_id_dependency),
    service: ClientCacheService = Depends(get_client_cache_service),
) -> dict[str, str]:
    return service.heartbeat(client_id)


@router.delete("")
def clear_client_cache(
    client_id: str = Depends(get_client_id_dependency),
    service: ClientCacheService = Depends(get_client_cache_service),
) -> dict[str, Any]:
    return service.clear_cache(client_id)
