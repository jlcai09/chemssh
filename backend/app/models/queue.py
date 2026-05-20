from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel


class QueueItem(BaseModel):
    job_id: str
    name: str = ""
    user: str = ""
    state: str = ""
    partition: str = ""
    nodes: Optional[int] = None
    cpus: Optional[int] = None
    time_used: str = ""
    time_limit: str = ""
    reason: str = ""
    workdir: Optional[str] = None


class QueueResponse(BaseModel):
    scheduler: str
    available: bool = True
    message: str = ""
    items: list[QueueItem]


class QueueJobDetailResponse(BaseModel):
    job_id: str
    detail: dict[str, Any]


QueueJobAction = Literal["hold", "release", "cancel"]


class CancelJobRequest(BaseModel):
    job_id: str


class QueueJobActionRequest(BaseModel):
    job_id: str
    action: QueueJobAction


class CancelJobResponse(BaseModel):
    success: bool
    scheduler: str
    job_id: str
    message: str


class QueueJobActionResponse(BaseModel):
    success: bool
    scheduler: str
    job_id: str
    action: QueueJobAction
    command: str
    message: str
