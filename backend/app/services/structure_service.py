from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import iread, read

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.core.security import WorkspaceSecurity
from backend.app.models.structure import AseFrame, AsePreviewResponse


STRUCTURE_BINARY_MEDIA_TYPE = "application/vnd.chemweb.structure+bin"
STRUCTURE_BINARY_MAGIC = b"CWB1"


@dataclass
class StructureSummary:
    n_frames: int
    n_atoms: int
    last_atoms: Atoms
    topology_stable: bool
    detected_format: str | None


class StructureService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.security = WorkspaceSecurity(settings.workspace.root)

    def preview(self, raw_path: str, fmt: str | None = None, *, force: bool = False) -> AsePreviewResponse:
        path = self._resolve_structure_file(raw_path, force=force)
        summary = self._scan_structure(path, fmt)
        frame_index = summary.n_frames - 1
        frame = self._frame_from_atoms(summary.last_atoms, frame_index)
        points = summary.n_atoms * summary.n_frames
        use_binary = (
            self.settings.viewer.ase.prefer_binary
            and summary.topology_stable
            and summary.n_frames > 1
        )

        return AsePreviewResponse(
            path=str(path),
            name=path.name,
            format=summary.detected_format,
            transport="binary-available" if use_binary else "json",
            is_trajectory=summary.n_frames > 1,
            n_frames=summary.n_frames,
            n_atoms=summary.n_atoms,
            initial_frame_index=frame_index,
            topology_stable=summary.topology_stable,
            size_limit_overridden=force,
            frame=frame,
        )

    def read_frame(self, raw_path: str, index: int, fmt: str | None = None, *, force: bool = False) -> AseFrame:
        if index < 0:
            raise AppError("INVALID_FRAME_INDEX", "Frame index must be greater than or equal to 0", 400)
        path = self._resolve_structure_file(raw_path, force=force)
        atoms = self._read_frame(path, index, fmt)
        return self._frame_from_atoms(atoms, index)

    def read_frame_chunk_binary(self, raw_path: str, start: int, count: int, fmt: str | None = None, *, force: bool = False) -> bytes:
        if start < 0:
            raise AppError("INVALID_FRAME_RANGE", "Chunk start must be greater than or equal to 0", 400)
        if count <= 0:
            raise AppError("INVALID_FRAME_RANGE", "Chunk count must be greater than 0", 400)

        path = self._resolve_structure_file(raw_path, force=force)
        summary = self._scan_structure(path, fmt)
        if not summary.topology_stable:
            raise AppError(
                "STRUCTURE_TOPOLOGY_UNSTABLE",
                "Binary frame chunks require a stable atom count and element order",
                409,
            )
        if start >= summary.n_frames:
            raise AppError("FRAME_INDEX_OUT_OF_RANGE", f"Frame start is outside range: {start}", 404)

        max_count = self.settings.viewer.ase.binary_chunk_frames
        safe_count = min(count, max_count, summary.n_frames - start)
        frames = self._read_frame_range(path, start, safe_count, fmt)
        if len(frames) != safe_count:
            raise AppError("FRAME_INDEX_OUT_OF_RANGE", "Requested frame chunk is incomplete", 404)
        return self._build_binary_payload(
            path=path,
            frames=frames,
            start=start,
            n_frames_total=summary.n_frames,
            detected_format=summary.detected_format,
        )

    def _resolve_structure_file(self, raw_path: str, *, force: bool = False) -> Path:
        if not self.settings.viewer.ase.enabled:
            raise AppError("ASE_VIEWER_DISABLED", "ASE structure preview is disabled", 400)

        path = self.security.resolve_path(raw_path)
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", f"File not found: {path}", 404)
        if not path.is_file():
            raise AppError("NOT_A_FILE", f"Path is not a file: {path}", 400)

        max_bytes = self.settings.viewer.max_file_size_mb * 1024 * 1024
        size = path.stat().st_size
        if not force and size > max_bytes:
            raise AppError(
                "STRUCTURE_FILE_TOO_LARGE",
                f"File is {size} bytes; structure preview limit is {max_bytes} bytes",
                413,
            )
        return path

    def _scan_structure(self, path: Path, fmt: str | None) -> StructureSummary:
        frames_seen = 0
        first_numbers: tuple[int, ...] | None = None
        n_atoms = 0
        last_atoms: Atoms | None = None
        topology_stable = True

        try:
            iterator = iread(str(path), index=":", format=fmt, do_not_split_by_at_sign=True)
            for atoms in iterator:
                self._validate_atoms(atoms, path)
                numbers = tuple(int(value) for value in atoms.get_atomic_numbers())
                if first_numbers is None:
                    first_numbers = numbers
                    n_atoms = len(atoms)
                elif numbers != first_numbers:
                    topology_stable = False
                frames_seen += 1
                if frames_seen > self.settings.viewer.ase.max_frames:
                    raise AppError(
                        "STRUCTURE_TOO_MANY_FRAMES",
                        f"Structure has more than {self.settings.viewer.ase.max_frames} frames",
                        413,
                    )
                last_atoms = atoms
        except AppError:
            raise
        except Exception as exc:
            raise AppError("STRUCTURE_PARSE_FAILED", f"ASE could not parse {path.name}: {exc}", 400) from exc

        if last_atoms is None or frames_seen == 0:
            raise AppError("STRUCTURE_PARSE_FAILED", f"ASE did not find any frames in {path.name}", 400)

        return StructureSummary(
            n_frames=frames_seen,
            n_atoms=n_atoms,
            last_atoms=last_atoms,
            topology_stable=topology_stable,
            detected_format=fmt,
        )

    def _read_frame(self, path: Path, index: int, fmt: str | None) -> Atoms:
        try:
            atoms = read(str(path), index=index, format=fmt, do_not_split_by_at_sign=True)
            if isinstance(atoms, list):
                if not atoms:
                    raise AppError("FRAME_INDEX_OUT_OF_RANGE", f"Frame index is outside range: {index}", 404)
                atoms = atoms[0]
            self._validate_atoms(atoms, path)
            return atoms
        except AppError:
            raise
        except Exception:
            pass

        try:
            for frame_index, atoms in enumerate(iread(str(path), index=":", format=fmt, do_not_split_by_at_sign=True)):
                if frame_index == index:
                    self._validate_atoms(atoms, path)
                    return atoms
        except Exception as exc:
            raise AppError("STRUCTURE_PARSE_FAILED", f"ASE could not parse {path.name}: {exc}", 400) from exc

        raise AppError("FRAME_INDEX_OUT_OF_RANGE", f"Frame index is outside range: {index}", 404)

    def _read_frame_range(self, path: Path, start: int, count: int, fmt: str | None) -> list[Atoms]:
        end = start + count
        frames: list[Atoms] = []
        try:
            iterator = iread(str(path), index=slice(start, end), format=fmt, do_not_split_by_at_sign=True)
            for atoms in iterator:
                self._validate_atoms(atoms, path)
                frames.append(atoms)
        except Exception:
            frames = []

        if frames:
            return frames[:count]

        try:
            for frame_index, atoms in enumerate(iread(str(path), index=":", format=fmt, do_not_split_by_at_sign=True)):
                if frame_index < start:
                    continue
                if frame_index >= end:
                    break
                self._validate_atoms(atoms, path)
                frames.append(atoms)
        except Exception as exc:
            raise AppError("STRUCTURE_PARSE_FAILED", f"ASE could not parse {path.name}: {exc}", 400) from exc

        return frames

    def _validate_atoms(self, atoms: Atoms, path: Path) -> None:
        atom_count = len(atoms)
        if atom_count <= 0:
            raise AppError("STRUCTURE_PARSE_FAILED", f"ASE found an empty frame in {path.name}", 400)
        if atom_count > self.settings.viewer.ase.max_atoms:
            raise AppError(
                "STRUCTURE_TOO_MANY_ATOMS",
                f"Structure has {atom_count} atoms; limit is {self.settings.viewer.ase.max_atoms}",
                413,
            )

    def _frame_from_atoms(self, atoms: Atoms, frame_index: int) -> AseFrame:
        digits = self.settings.viewer.ase.json_round_digits
        positions = _rounded_float32_list(atoms.get_positions(), digits)
        cell = _rounded_float32_list(atoms.cell.array, digits)
        energy, fmax = _extract_energy_fmax(atoms)

        return AseFrame(
            frame_index=frame_index,
            positions=positions,
            cell=cell,
            pbc=[bool(value) for value in atoms.get_pbc()],
            tags=[int(value) for value in np.asarray(atoms.get_tags(), dtype=np.int32).tolist()],
            fixed_indices=_extract_fixed_indices(atoms),
            energy=energy,
            fmax=fmax,
            symbols=atoms.get_chemical_symbols(),
            numbers=[int(value) for value in atoms.get_atomic_numbers()],
        )

    def _build_binary_payload(
        self,
        *,
        path: Path,
        frames: list[Atoms],
        start: int,
        n_frames_total: int,
        detected_format: str | None,
    ) -> bytes:
        first = frames[0]
        first_numbers = tuple(int(value) for value in first.get_atomic_numbers())
        n_atoms = len(first)
        count = len(frames)

        positions = np.empty((count, n_atoms, 3), dtype="<f4")
        cells = np.empty((count, 3, 3), dtype="<f4")
        tags = np.empty((count, n_atoms), dtype="<i4")
        fixed_mask = np.zeros((count, n_atoms), dtype=np.uint8)
        energy = np.full((count,), np.nan, dtype="<f4")
        fmax = np.full((count,), np.nan, dtype="<f4")

        for local_index, atoms in enumerate(frames):
            numbers = tuple(int(value) for value in atoms.get_atomic_numbers())
            if len(atoms) != n_atoms or numbers != first_numbers:
                raise AppError(
                    "STRUCTURE_TOPOLOGY_UNSTABLE",
                    "Binary frame chunks require a stable atom count and element order",
                    409,
                )
            positions[local_index] = np.asarray(atoms.get_positions(), dtype="<f4")
            cells[local_index] = np.asarray(atoms.cell.array, dtype="<f4")
            tags[local_index] = np.asarray(atoms.get_tags(), dtype="<i4")
            for atom_index in _extract_fixed_indices(atoms):
                fixed_mask[local_index, atom_index] = 1
            frame_energy, frame_fmax = _extract_energy_fmax(atoms)
            if frame_energy is not None:
                energy[local_index] = frame_energy
            if frame_fmax is not None:
                fmax[local_index] = frame_fmax

        arrays: dict[str, dict[str, Any]] = {}
        binary_parts: list[bytes] = []
        offset = 0

        def add_array(name: str, array: np.ndarray, *, alignment: int) -> None:
            nonlocal offset
            if alignment > 1:
                padding_size = (alignment - (offset % alignment)) % alignment
                if padding_size:
                    binary_parts.append(b"\0" * padding_size)
                    offset += padding_size
            contiguous = np.ascontiguousarray(array)
            data = contiguous.tobytes()
            arrays[name] = {
                "offset": offset,
                "byte_length": len(data),
                "shape": list(contiguous.shape),
            }
            binary_parts.append(data)
            offset += len(data)

        add_array("positions", positions, alignment=4)
        add_array("cells", cells, alignment=4)
        add_array("tags", tags, alignment=4)
        add_array("energy", energy, alignment=4)
        add_array("fmax", fmax, alignment=4)
        add_array("fixed_mask", fixed_mask, alignment=1)

        header = {
            "version": 1,
            "dtype": "float32-le",
            "int_dtype": "int32-le",
            "start": start,
            "count": count,
            "n_frames_total": n_frames_total,
            "n_atoms": n_atoms,
            "topology_stable": True,
            "path": str(path),
            "name": path.name,
            "format": detected_format,
            "symbols": first.get_chemical_symbols(),
            "numbers": [int(value) for value in first_numbers],
            "pbc": [bool(value) for value in first.get_pbc()],
            "arrays": arrays,
            "nan_means_null": ["energy", "fmax"],
        }
        header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header_padding = b"\0" * ((4 - (len(header_bytes) % 4)) % 4)

        return (
            STRUCTURE_BINARY_MAGIC
            + struct.pack("<I", len(header_bytes))
            + header_bytes
            + header_padding
            + b"".join(binary_parts)
        )


def _rounded_float32_list(values: Any, digits: int) -> list[list[float]]:
    array = np.asarray(values, dtype=np.float32).astype(np.float64)
    return np.round(array, digits).tolist()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _extract_energy_fmax(atoms: Atoms) -> tuple[float | None, float | None]:
    calc = getattr(atoms, "calc", None)
    results = getattr(calc, "results", {}) or {}

    energy = None
    for key in ("energy", "free_energy"):
        if key in results:
            energy = _safe_float(results.get(key))
            if energy is not None:
                break

    forces = results.get("forces")
    if forces is None:
        return energy, None

    force_array = np.asarray(forces, dtype=np.float32)
    if force_array.ndim != 2 or force_array.shape[1] != 3 or force_array.size == 0:
        return energy, None
    fmax = float(np.max(np.linalg.norm(force_array, axis=1)))
    if not math.isfinite(fmax):
        return energy, None
    return energy, fmax


def _extract_fixed_indices(atoms_image: Atoms) -> list[int]:
    fixed: set[int] = set()
    constraints = getattr(atoms_image, "constraints", []) or []

    for constraint in constraints:
        if constraint.__class__.__name__ != "FixAtoms":
            continue
        if hasattr(constraint, "get_indices"):
            indices = constraint.get_indices()
        else:
            indices = getattr(constraint, "index", [])
        for index in np.asarray(indices, dtype=np.int32).reshape(-1):
            atom_index = int(index)
            if 0 <= atom_index < len(atoms_image):
                fixed.add(atom_index)

    return sorted(fixed)
