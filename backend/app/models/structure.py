from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AseFrame(BaseModel):
    frame_index: int
    positions: list[list[float]]
    cell: list[list[float]]
    pbc: list[bool]
    tags: list[int]
    fixed_indices: list[int] = Field(default_factory=list)
    energy: Optional[float] = None
    fmax: Optional[float] = None
    symbols: Optional[list[str]] = None
    numbers: Optional[list[int]] = None


class AsePreviewResponse(BaseModel):
    path: str
    name: str
    format: Optional[str] = None
    transport: Literal["json", "binary-available"]
    is_trajectory: bool
    n_frames: int
    n_atoms: int
    initial_frame_index: int
    topology_stable: bool = True
    size_limit_overridden: bool = False
    frame: AseFrame
    file_incomplete: bool = False
    scan_completed: bool = True
    warnings: list[str] = Field(default_factory=list)


class AseFrameChunkResponse(BaseModel):
    start: int
    count: int
    frames: list[AseFrame]
