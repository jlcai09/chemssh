from __future__ import annotations

from pathlib import Path
from typing import Optional


STRUCTURE_EXTENSIONS = {
    ".xyz": "xyz",
    ".pdb": "pdb",
    ".mol": "mol",
    ".sdf": "sdf",
    ".cif": "cif",
    ".traj": "traj",
    ".extxyz": "extxyz",
    ".vasp": "vasp",
    ".xsf": "xsf",
    ".cube": "cube",
    ".gen": "gen",
    ".db": "db",
    ".lammps": "lammps",
    ".dump": "lammps-dump-text",
    ".xml": "xml",
    ".gjf": "gaussian-in",
    ".com": "gaussian-in",
    ".fdf": "fdf",
    ".pwi": "espresso-in",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".log",
    ".out",
    ".in",
    ".inp",
    ".sh",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".dat",
    ".csv",
    ".err",
}

TEXT_NAMES = {
    "INCAR",
    "KPOINTS",
    "OSZICAR",
    "POTCAR",
}

ASE_STRUCTURE_NAMES = {
    "OUTCAR",
    "XDATCAR",
    "vasp.xml",
}


def is_forced_structure_name(path: Path) -> bool:
    name = path.name.upper()
    return "POSCAR" in name or "CONTCAR" in name


def detect_preview(path: Path, *, is_dir: bool = False) -> tuple[str, Optional[str]]:
    if is_dir:
        return "directory", None

    if is_forced_structure_name(path):
        return "structure", None

    if path.name.upper() in ASE_STRUCTURE_NAMES or path.name.lower() in ASE_STRUCTURE_NAMES:
        return "structure", None

    suffix = path.suffix.lower()
    if suffix in STRUCTURE_EXTENSIONS:
        return "structure", STRUCTURE_EXTENSIONS[suffix]
    if suffix in TEXT_EXTENSIONS or path.name.upper() in TEXT_NAMES:
        return "text", None
    return "file", None
