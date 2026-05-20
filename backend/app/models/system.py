from __future__ import annotations

from pydantic import BaseModel


class SystemInfo(BaseModel):
    username: str
    hostname: str
    cwd: str
    project_version: str
    python_version: str
    scheduler: str
    workspace_root: str
