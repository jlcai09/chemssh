from __future__ import annotations

import re

from fastapi import Depends, Header

from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import AppError
from backend.app.providers.scheduler.base import SchedulerProvider
from backend.app.providers.scheduler.pbs import PbsProvider
from backend.app.providers.scheduler.slurm import SlurmProvider
from backend.app.services.file_service import FileService
from backend.app.services.job_service import JobService
from backend.app.services.client_cache_service import ClientCacheService
from backend.app.services.queue_service import QueueService
from backend.app.services.structure_service import StructureService


CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def get_settings_dependency() -> Settings:
    return get_settings()


def validate_client_id(client_id: str | None) -> str:
    if not client_id:
        raise AppError("CLIENT_ID_REQUIRED", "Client id is required", 400)
    if not CLIENT_ID_RE.match(client_id):
        raise AppError("INVALID_CLIENT_ID", "Invalid client id", 400)
    return client_id


def get_client_id_dependency(
    client_id: str | None = Header(default=None, alias="X-ChemSSH-Client-Id"),
) -> str:
    return validate_client_id(client_id)


def get_file_service(settings: Settings = Depends(get_settings_dependency)) -> FileService:
    return FileService(settings)


def get_structure_service(settings: Settings = Depends(get_settings_dependency)) -> StructureService:
    return StructureService(settings)


def get_client_cache_service(settings: Settings = Depends(get_settings_dependency)) -> ClientCacheService:
    return ClientCacheService(settings)


def get_scheduler_provider(settings: Settings = Depends(get_settings_dependency)) -> SchedulerProvider:
    if settings.scheduler.type == "pbs":
        return PbsProvider()
    return SlurmProvider()


def get_queue_service(
    provider: SchedulerProvider = Depends(get_scheduler_provider),
) -> QueueService:
    return QueueService(provider)


def get_job_service(
    settings: Settings = Depends(get_settings_dependency),
    provider: SchedulerProvider = Depends(get_scheduler_provider),
) -> JobService:
    return JobService(settings, provider)
