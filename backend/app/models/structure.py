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


FragmentQueryMode = Literal[
    "connected",
    "same_formula",
    "within_radius",
    "whole_molecule_wrap",
]


class AseFragmentRequest(BaseModel):
    path: str
    format: Optional[str] = None
    force: bool = False
    frame_index: int = Field(default=0, ge=0)
    bond_scale: float = Field(default=1.25, ge=0.4, le=3.0)
    seed_atoms: list[int] = Field(default_factory=list)
    mode: FragmentQueryMode = "connected"
    use_pbc: bool = True
    radius: Optional[float] = Field(default=None, gt=0.0, le=50.0)
    expand_fragments: bool = True


class AseFragmentResponse(BaseModel):
    frame_index: int
    mode: FragmentQueryMode
    atom_indices: list[int] = Field(default_factory=list)
    fragment_count: int = 0
    formulas: list[str] = Field(default_factory=list)
    wrapped_positions: Optional[list[list[float]]] = None


AtomDisplayModeStr = Literal["stick", "sphere", "line", "dim", "hidden"]
DynamicRuleType = Literal[
    "formula",
    "shell",
    "coordination",
    "slice",
    "minority",
    "element_fixed",
]
CoordOperator = Literal["eq", "ne", "lt", "le", "gt", "ge"]


class DynamicDisplayRule(BaseModel):
    id: str
    enabled: bool = True
    type: DynamicRuleType
    style: AtomDisplayModeStr = "hidden"
    # formula
    formulas: list[str] = Field(default_factory=list)
    # shell
    anchor_type: Literal["atoms", "elements"] = "elements"
    anchor_atoms: list[int] = Field(default_factory=list)
    anchor_elements: list[str] = Field(default_factory=list)
    radius: float = Field(default=3.5, gt=0.0, le=50.0)
    outside: bool = False
    expand_fragments: bool = True
    # coordination
    elements: list[str] = Field(default_factory=list)
    operator: CoordOperator = "ne"
    count: int = Field(default=2, ge=0, le=32)
    # slice
    axis: Literal["x", "y", "z"] = "z"
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    fractional: bool = False
    # minority / reactive species
    max_fraction: float = Field(default=0.05, gt=0.0, le=1.0)
    invert: bool = False
    # element_fixed
    fixed_only: bool = False


class AseDynamicDisplayRequest(BaseModel):
    path: str
    format: Optional[str] = None
    force: bool = False
    frame_index: int = Field(default=0, ge=0)
    bond_scale: float = Field(default=1.25, ge=0.4, le=3.0)
    use_pbc: bool = True
    default_style: AtomDisplayModeStr = "stick"
    rules: list[DynamicDisplayRule] = Field(default_factory=list)


class AseDynamicDisplayResponse(BaseModel):
    frame_index: int
    atom_modes: list[int] = Field(default_factory=list)
    rule_match_counts: dict[str, int] = Field(default_factory=dict)
    available_formulas: list[str] = Field(default_factory=list)

