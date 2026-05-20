from __future__ import annotations

import getpass
import platform
import sys
from pathlib import Path

from fastapi import APIRouter, Depends

from backend.app import __version__
from backend.app.core.config import Settings
from backend.app.dependencies import get_settings_dependency
from backend.app.models.system import SystemInfo


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=SystemInfo)
def system_info(settings: Settings = Depends(get_settings_dependency)) -> SystemInfo:
    return SystemInfo(
        username=getpass.getuser(),
        hostname=platform.node(),
        cwd=str(Path.cwd()),
        project_version=__version__,
        python_version=platform.python_version() or sys.version.split()[0],
        scheduler=settings.scheduler.type,
        workspace_root=str(settings.workspace.root),
    )
