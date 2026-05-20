from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateTerminalSessionRequest(BaseModel):
    cwd: Optional[str] = None
    shell: Optional[str] = None
    rows: Optional[int] = Field(default=None, ge=2, le=200)
    cols: Optional[int] = Field(default=None, ge=20, le=500)


class TerminalSessionResponse(BaseModel):
    session_id: str
    cwd: str
    shell: str
    created_at: datetime
    last_active_at: datetime
    alive: bool
    clients: int = 0


class TerminalSessionListResponse(BaseModel):
    items: list[TerminalSessionResponse]


class TerminalCloseResponse(BaseModel):
    success: bool = True
