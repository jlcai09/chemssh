from __future__ import annotations

from pathlib import Path

from ase import Atoms
from ase.constraints import FixAtoms
from ase.io import write
from fastapi.testclient import TestClient

from backend.app.core.config import Settings, WorkspaceConfig
from backend.app.main import create_app


def make_client(root: Path) -> TestClient:
    return TestClient(create_app(Settings(workspace=WorkspaceConfig(root=root))))


def _write_selective_poscar(directory: Path) -> None:
    (directory / "POSCAR").write_text(
        "selective\n"
        "1.0\n"
        "10 0 0\n"
        "0 10 0\n"
        "0 0 10\n"
        "H O\n"
        "1 1\n"
        "Selective dynamics\n"
        "Direct\n"
        "0 0 0 F F F\n"
        "0.2 0 0 T T T\n",
        encoding="utf-8",
    )


def _write_outcar(directory: Path, steps: int = 2) -> None:
    lines = [
        " POTCAR:    PAW_PBE H 15Jun2001",
        " POTCAR:    PAW_PBE O 08Apr2002",
        " POTCAR:    PAW_PBE H 15Jun2001",
        " POTCAR:    PAW_PBE O 08Apr2002",
        "   NIONS = 2",
        "   ions per type = 1 1",
    ]
    for step in range(steps):
        lines.extend(
            [
                f" Iteration  {step + 1}",
                " direct lattice vectors",
                " 10.000000 0.000000 0.000000",
                " 0.000000 10.000000 0.000000",
                " 0.000000 0.000000 10.000000",
                " POSITION                                       TOTAL-FORCE (eV/Angst)",
                " -----------------------------------------------------------------------------------",
                f" 0.0 0.0 0.0 9.0 0.0 {float(step)}",
                " 0.2 0.0 0.0 0.2 0.0 0.0",
            ]
        )
    (directory / "OUTCAR").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_traj(directory: Path, frames: int = 3) -> None:
    images = []
    for index in range(frames):
        atoms = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.2 + index * 0.01, 0.0, 0.0]], cell=[10, 10, 10], pbc=True)
        atoms.set_constraint(FixAtoms(indices=[0]))
        images.append(atoms)
    write(str(directory / "optimized.traj"), images)


def test_outcar_stats_excludes_fixed_atoms(tmp_path: Path) -> None:
    workdir = tmp_path / "job"
    workdir.mkdir()
    _write_selective_poscar(workdir)
    _write_outcar(workdir, steps=2)

    response = make_client(tmp_path).post("/api/queue/vasp-stats", json={"workdirs": [str(workdir)]})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["status"] == "ok"
    assert item["steps"] == 2
    assert item["steps_source"] == "outcar"
    assert item["fmax_source"] == "outcar"
    assert item["fmax"] is not None
    assert abs(item["fmax"] - 0.2) < 1e-6


def test_traj_takes_priority_for_steps_and_falls_back_for_fmax(tmp_path: Path) -> None:
    workdir = tmp_path / "job"
    workdir.mkdir()
    _write_selective_poscar(workdir)
    _write_outcar(workdir, steps=2)
    _write_traj(workdir, frames=3)

    response = make_client(tmp_path).post("/api/queue/vasp-stats", json={"workdirs": [str(workdir)]})

    item = response.json()["items"][0]
    assert item["status"] == "ok"
    assert item["steps"] == 3
    assert item["steps_source"] == "traj"
    assert item["fmax_source"] == "outcar"
    assert abs(item["fmax"] - 0.2) < 1e-6


def test_traj_only_reports_length_without_forces(tmp_path: Path) -> None:
    workdir = tmp_path / "job"
    workdir.mkdir()
    _write_traj(workdir, frames=4)

    response = make_client(tmp_path).post("/api/queue/vasp-stats", json={"workdirs": [str(workdir)]})

    item = response.json()["items"][0]
    assert item["status"] == "ok"
    assert item["steps"] == 4
    assert item["steps_source"] == "traj"
    assert item["fmax"] is None
    assert item["fmax_source"] is None


def test_missing_directory_reports_missing_and_dedupes(tmp_path: Path) -> None:
    workdir = tmp_path / "empty"
    workdir.mkdir()

    response = make_client(tmp_path).post(
        "/api/queue/vasp-stats",
        json={"workdirs": [str(workdir), str(workdir)]},
    )

    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "missing"


def test_path_outside_workspace_is_rejected_per_item(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-job"
    outside.mkdir(exist_ok=True)

    response = make_client(tmp_path).post("/api/queue/vasp-stats", json={"workdirs": [str(outside)]})

    item = response.json()["items"][0]
    assert item["status"] == "error"
    assert "outside workspace" in item["message"]
