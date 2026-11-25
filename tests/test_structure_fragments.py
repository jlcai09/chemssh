from __future__ import annotations

from pathlib import Path

import numpy as np
from ase import Atoms
from ase.io import write as ase_write
from fastapi.testclient import TestClient

from backend.app.core.config import Settings, WorkspaceConfig
from backend.app.main import create_app


def _make_client(root: Path) -> TestClient:
    settings = Settings(workspace=WorkspaceConfig(root=root))
    return TestClient(create_app(settings))


def _build_solvated_box() -> Atoms:
    """10x10x10 cubic box with:
    - atom 0: Na+ at (5, 5, 5)
    - atoms 1,2,3: H2O #1 near Na+ at ~2.8 A (not bonded to Na at bond_scale=1.0)
    - atoms 4,5,6: H2O #2 in bulk at (2, 2, 2)
    - atoms 7,8,9: H2O #3 split across the x=0/10 periodic boundary
    """
    positions = [
        # 0: Na
        [5.0, 5.0, 5.0],
        # 1..3: H2O #1 (near Na, dist ~2.9 A)
        [7.9, 5.0, 5.0],
        [8.5, 5.75, 5.0],
        [8.5, 4.25, 5.0],
        # 4..6: H2O #2 (bulk)
        [2.0, 2.0, 2.0],
        [2.75, 2.58, 2.0],
        [1.25, 2.58, 2.0],
        # 7..9: H2O #3 split across PBC (O at x=9.8, one H wrapped to x=0.45)
        [9.8, 8.0, 8.0],
        [0.45, 8.65, 8.0],
        [9.15, 8.65, 8.0],
    ]
    symbols = ["Na", "O", "H", "H", "O", "H", "H", "O", "H", "H"]
    return Atoms(symbols=symbols, positions=positions, cell=[10.0, 10.0, 10.0], pbc=True)


def test_connected_and_same_formula_across_pbc(tmp_path: Path) -> None:
    atoms = _build_solvated_box()
    traj_path = tmp_path / "box.extxyz"
    ase_write(traj_path, [atoms, atoms], format="extxyz")

    client = _make_client(tmp_path)

    # 1. Connected fragment on PBC-split water (atom 8 is H at x=0.45)
    resp = client.post(
        "/api/structures/ase/fragments",
        json={
            "path": str(traj_path),
            "frame_index": 0,
            "bond_scale": 1.15,
            "seed_atoms": [8],
            "mode": "connected",
            "use_pbc": True,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["atom_indices"] == [7, 8, 9]
    assert data["fragment_count"] == 1
    assert data["formulas"] == ["H2O"]

    # 2. Same formula from one bulk water atom should select all 3 water molecules (9 atoms), excluding Na (0)
    resp2 = client.post(
        "/api/structures/ase/fragments",
        json={
            "path": str(traj_path),
            "frame_index": 1,
            "bond_scale": 1.15,
            "seed_atoms": [4],
            "mode": "same_formula",
            "use_pbc": True,
        },
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["atom_indices"] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert data2["fragment_count"] == 3
    assert data2["formulas"] == ["H2O"]


def test_within_radius_and_whole_molecule_wrap(tmp_path: Path) -> None:
    atoms = _build_solvated_box()
    xyz_path = tmp_path / "box.extxyz"
    ase_write(xyz_path, atoms, format="extxyz")
    client = _make_client(tmp_path)

    # 1. Within 3.1 A of Na (atom 0), only O of H2O #1 (atom 1) is inside,
    #    expand_fragments=False -> [0, 1]; expand_fragments=True -> [0, 1, 2, 3]
    resp_raw = client.post(
        "/api/structures/ase/fragments",
        json={
            "path": str(xyz_path),
            "frame_index": 0,
            "bond_scale": 1.15,
            "seed_atoms": [0],
            "mode": "within_radius",
            "radius": 3.1,
            "expand_fragments": False,
        },
    )
    assert resp_raw.status_code == 200
    assert resp_raw.json()["atom_indices"] == [0, 1]

    resp_expanded = client.post(
        "/api/structures/ase/fragments",
        json={
            "path": str(xyz_path),
            "frame_index": 0,
            "bond_scale": 1.15,
            "seed_atoms": [0],
            "mode": "within_radius",
            "radius": 3.1,
            "expand_fragments": True,
        },
    )
    assert resp_expanded.status_code == 200
    assert resp_expanded.json()["atom_indices"] == [0, 1, 2, 3]

    # 2. Whole-molecule wrap should stitch H2O #3 back together so both O-H distances are ~0.92 A
    resp_wrap = client.post(
        "/api/structures/ase/fragments",
        json={
            "path": str(xyz_path),
            "frame_index": 0,
            "bond_scale": 1.15,
            "mode": "whole_molecule_wrap",
            "use_pbc": True,
        },
    )
    assert resp_wrap.status_code == 200
    wrapped = np.asarray(resp_wrap.json()["wrapped_positions"], dtype=np.float64)
    assert wrapped.shape == (10, 3)
    d_oh1 = float(np.linalg.norm(wrapped[7] - wrapped[8]))
    d_oh2 = float(np.linalg.norm(wrapped[7] - wrapped[9]))
    assert 0.8 < d_oh1 < 1.2
    assert 0.8 < d_oh2 < 1.2


def test_dynamic_display_all_six_rule_types(tmp_path: Path) -> None:
    frame0 = _build_solvated_box()
    # Frame 1: move H2O #2 (atoms 4,5,6) close to Na (atom 0) to simulate solvent exchange,
    # and detach H2O #1 further away
    frame1 = frame0.copy()
    pos1 = frame1.get_positions()
    pos1[1:4] += np.array([1.5, 0.0, 0.0])  # H2O #1 moves out of 3.1 A shell
    pos1[4:7] = np.array([[7.5, 5.0, 5.0], [8.1, 5.75, 5.0], [8.1, 4.25, 5.0]])  # H2O #2 enters shell
    frame1.set_positions(pos1)

    traj_path = tmp_path / "exchange.extxyz"
    ase_write(traj_path, [frame0, frame1], format="extxyz")
    client = _make_client(tmp_path)

    # Rule stack:
    # 1. formula H2O -> hidden (4)
    # 2. shell within 3.1 A of Na (expand_fragments=True) -> stick (0)  [overrides H2O hide for solvation shell]
    # 3. coordination of Na == 0 -> sphere (1)
    # 4. slice z >= 7.0 -> dim (3)  [affects H2O #3 at z=8.0]
    rules = [
        {"id": "r1", "enabled": True, "type": "formula", "style": "hidden", "formulas": ["H2O"]},
        {
            "id": "r2",
            "enabled": True,
            "type": "shell",
            "style": "stick",
            "anchor_type": "elements",
            "anchor_elements": ["Na"],
            "radius": 3.1,
            "outside": False,
            "expand_fragments": True,
        },
        {
            "id": "r3",
            "enabled": True,
            "type": "coordination",
            "style": "sphere",
            "elements": ["Na"],
            "operator": "eq",
            "count": 0,
        },
        {
            "id": "r4",
            "enabled": True,
            "type": "slice",
            "style": "dim",
            "axis": "z",
            "min_val": 7.0,
            "outside": False,
            "expand_fragments": True,
        },
    ]

    resp0 = client.post(
        "/api/structures/ase/dynamic-display",
        json={"path": str(traj_path), "frame_index": 0, "bond_scale": 1.15, "default_style": "stick", "rules": rules},
    )
    assert resp0.status_code == 200, resp0.text
    d0 = resp0.json()
    # Frame 0: Na(0)=sphere(1), H2O#1(1..3)=stick(0), H2O#2(4..6)=hidden(4), H2O#3(7..9)=dim(3)
    assert d0["atom_modes"] == [1, 0, 0, 0, 4, 4, 4, 3, 3, 3]
    assert d0["rule_match_counts"]["r1"] == 9
    assert d0["rule_match_counts"]["r2"] == 4
    assert "H2O" in d0["available_formulas"]

    resp1 = client.post(
        "/api/structures/ase/dynamic-display",
        json={"path": str(traj_path), "frame_index": 1, "bond_scale": 1.15, "default_style": "stick", "rules": rules},
    )
    assert resp1.status_code == 200, resp1.text
    d1 = resp1.json()
    # Frame 1: H2O#1 moved out -> hidden(4); H2O#2 moved within 2.5 A -> coordinates with Na
    # so Na coordination becomes 1 (no longer matches r3 count==0) and stays stick(0)!
    assert d1["atom_modes"] == [0, 4, 4, 4, 0, 0, 0, 3, 3, 3]
    assert d1["rule_match_counts"]["r3"] == 0

    # Also verify minority + element_fixed rules
    resp_extra = client.post(
        "/api/structures/ase/dynamic-display",
        json={
            "path": str(traj_path),
            "frame_index": 0,
            "bond_scale": 1.15,
            "default_style": "dim",
            "rules": [
                {"id": "m1", "enabled": True, "type": "minority", "style": "sphere", "max_fraction": 0.2, "invert": False},
                {"id": "e1", "enabled": True, "type": "element_fixed", "style": "line", "elements": ["H"], "fixed_only": False},
            ],
        },
    )
    assert resp_extra.status_code == 200, resp_extra.text
    modes_extra = resp_extra.json()["atom_modes"]
    assert modes_extra[0] == 1  # Na (10% <= 20%) -> sphere
    assert modes_extra[2] == 2  # H -> line
    assert modes_extra[1] == 3  # O -> default dim

