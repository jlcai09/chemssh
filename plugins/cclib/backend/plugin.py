from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ase.data import chemical_symbols
from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel

from backend.app.core.errors import AppError
from backend.app.models.structure import AseFrame, AseFrameChunkResponse
from backend.app.services.structure_service import STRUCTURE_BINARY_MAGIC, STRUCTURE_BINARY_MEDIA_TYPE


HARTREE_PER_BOHR_TO_EV_PER_ANGSTROM = 51.422067476325886


class ProbeItem(BaseModel):
    name: str | None = None
    path: str | None = None
    type: str | None = None
    extension: str | None = None
    preview_type: str | None = None


class ProbeRequest(BaseModel):
    path: str
    item: ProbeItem | None = None


@dataclass
class ParsedCclib:
    path: Path
    name: str
    numbers: list[int]
    symbols: list[str]
    positions: np.ndarray
    energies: list[float | None]
    fmax: list[float | None]
    metadata: dict[str, Any]
    size_limit_overridden: bool

    @property
    def n_frames(self) -> int:
        return int(self.positions.shape[0])

    @property
    def n_atoms(self) -> int:
        return int(self.positions.shape[1])


class CclibPlugin:
    def __init__(self, context: Any) -> None:
        self.context = context
        self.router = APIRouter()
        self._cache: dict[str, tuple[tuple[int, int], ParsedCclib]] = {}
        self._register_routes()

    def on_activate(self) -> None:
        self.context.logger.info("cclib plugin activated")

    def on_deactivate(self) -> None:
        self.context.logger.info("cclib plugin deactivated")

    def _register_routes(self) -> None:
        self.router.post("/probe")(self.probe)
        self.router.get("/structures/preview")(self.preview)
        self.router.get("/structures/frame")(self.frame)
        self.router.get("/structures/frames")(self.frames_json)
        self.router.get("/structures/frames.bin")(self.frames_binary)

    def probe(self, request: ProbeRequest) -> dict[str, Any]:
        path = self._resolve_existing_file(request.path, check_size=False)
        try:
            from cclib.io import ccopen
        except ImportError:
            return {
                "can_preview": False,
                "handler": "cclib-output",
                "program": None,
                "reason": "cclib is not installed for this plugin",
            }

        try:
            parser = ccopen(str(path))
        except Exception as exc:
            return {
                "can_preview": False,
                "handler": "cclib-output",
                "program": None,
                "reason": str(exc),
            }

        return {
            "can_preview": parser is not None,
            "handler": "cclib-output",
            "program": parser.__class__.__name__ if parser is not None else None,
            "reason": None if parser is not None else "cclib did not recognize this file",
        }

    def preview(self, path: str, force: bool = Query(default=False)) -> dict[str, Any]:
        parsed = self._parse(path, force=force)
        frame_index = parsed.n_frames - 1
        use_binary = (
            self.context.settings.viewer.ase.prefer_binary
            and parsed.n_frames > 1
        )
        return {
            "path": str(parsed.path),
            "name": parsed.name,
            "format": "cclib-output",
            "transport": "binary-available" if use_binary else "json",
            "is_trajectory": parsed.n_frames > 1,
            "n_frames": parsed.n_frames,
            "n_atoms": parsed.n_atoms,
            "initial_frame_index": frame_index,
            "topology_stable": True,
            "size_limit_overridden": parsed.size_limit_overridden,
            "frame": self._frame(parsed, frame_index).model_dump(),
            "metadata": parsed.metadata,
        }

    def frame(self, path: str, index: int = Query(ge=0), force: bool = Query(default=False)) -> AseFrame:
        parsed = self._parse(path, force=force)
        if index >= parsed.n_frames:
            raise AppError("FRAME_INDEX_OUT_OF_RANGE", f"Frame index is outside range: {index}", 404)
        return self._frame(parsed, index)

    def frames_json(
        self,
        path: str,
        start: int = Query(ge=0),
        count: int = Query(gt=0),
        force: bool = Query(default=False),
    ) -> AseFrameChunkResponse:
        parsed = self._parse(path, force=force)
        if start >= parsed.n_frames:
            raise AppError("FRAME_INDEX_OUT_OF_RANGE", f"Frame start is outside range: {start}", 404)
        safe_count = min(count, self.context.settings.viewer.ase.binary_chunk_frames, parsed.n_frames - start)
        frames = [self._frame(parsed, index) for index in range(start, start + safe_count)]
        return AseFrameChunkResponse(start=start, count=len(frames), frames=frames)

    def frames_binary(
        self,
        path: str,
        start: int = Query(ge=0),
        count: int = Query(gt=0),
        force: bool = Query(default=False),
    ) -> Response:
        parsed = self._parse(path, force=force)
        if start >= parsed.n_frames:
            raise AppError("FRAME_INDEX_OUT_OF_RANGE", f"Frame start is outside range: {start}", 404)
        safe_count = min(count, self.context.settings.viewer.ase.binary_chunk_frames, parsed.n_frames - start)
        return Response(
            content=self._binary_payload(parsed, start, safe_count),
            media_type=STRUCTURE_BINARY_MEDIA_TYPE,
        )

    def _resolve_existing_file(self, raw_path: str, *, check_size: bool, force: bool = False) -> Path:
        path = self.context.workspace_security.resolve_path(raw_path)
        if not path.exists():
            raise AppError("FILE_NOT_FOUND", f"File not found: {path}", 404)
        if not path.is_file():
            raise AppError("NOT_A_FILE", f"Path is not a file: {path}", 400)
        if check_size:
            max_bytes = self.context.settings.viewer.max_file_size_mb * 1024 * 1024
            size = path.stat().st_size
            if not force and size > max_bytes:
                raise AppError(
                    "STRUCTURE_FILE_TOO_LARGE",
                    f"File is {size} bytes; structure preview limit is {max_bytes} bytes",
                    413,
                )
        return path

    def _parse(self, raw_path: str, *, force: bool = False) -> ParsedCclib:
        path = self._resolve_existing_file(raw_path, check_size=True, force=force)
        stat = path.stat()
        cache_key = str(path)
        version = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(cache_key)
        if cached and cached[0] == version:
            cached[1].size_limit_overridden = force
            return cached[1]

        try:
            from cclib.io import ccread
        except ImportError as exc:
            raise AppError("PLUGIN_DEPENDENCY_MISSING", "cclib is not installed for this plugin", 500) from exc

        try:
            data = ccread(str(path))
        except Exception as exc:
            raise AppError("CCLIB_PARSE_FAILED", f"cclib could not parse {path.name}: {exc}", 400) from exc
        if data is None:
            raise AppError("CCLIB_PARSE_FAILED", f"cclib did not recognize {path.name}", 400)

        atomcoords = getattr(data, "atomcoords", None)
        atomnos = getattr(data, "atomnos", None)
        if atomcoords is None or atomnos is None:
            raise AppError("CCLIB_NO_STRUCTURE", f"cclib found no atom coordinates in {path.name}", 400)

        positions = np.asarray(atomcoords, dtype=np.float32)
        if positions.ndim == 2:
            positions = positions.reshape((1, positions.shape[0], positions.shape[1]))
        if positions.ndim != 3 or positions.shape[2] != 3:
            raise AppError("CCLIB_NO_STRUCTURE", "cclib returned coordinates with an unexpected shape", 400)

        numbers = [int(value) for value in np.asarray(atomnos, dtype=np.int32).reshape(-1).tolist()]
        if len(numbers) != positions.shape[1]:
            raise AppError("CCLIB_TOPOLOGY_MISMATCH", "Atom count does not match coordinate frames", 400)
        if len(numbers) > self.context.settings.viewer.ase.max_atoms:
            raise AppError(
                "STRUCTURE_TOO_MANY_ATOMS",
                f"Structure has {len(numbers)} atoms; limit is {self.context.settings.viewer.ase.max_atoms}",
                413,
            )
        if positions.shape[0] > self.context.settings.viewer.ase.max_frames:
            raise AppError(
                "STRUCTURE_TOO_MANY_FRAMES",
                f"Structure has more than {self.context.settings.viewer.ase.max_frames} frames",
                413,
            )

        parsed = ParsedCclib(
            path=path,
            name=path.name,
            numbers=numbers,
            symbols=[_symbol(number) for number in numbers],
            positions=positions,
            energies=_align_optional_values(getattr(data, "scfenergies", None), positions.shape[0]),
            fmax=self._extract_fmax(data, positions.shape[0]),
            metadata=self._metadata(data),
            size_limit_overridden=force,
        )
        self._cache[cache_key] = (version, parsed)
        return parsed

    def _frame(self, parsed: ParsedCclib, index: int) -> AseFrame:
        digits = self.context.settings.viewer.ase.json_round_digits
        return AseFrame(
            frame_index=index,
            positions=np.round(parsed.positions[index].astype(np.float64), digits).tolist(),
            cell=_zero_cell(),
            pbc=[False, False, False],
            tags=[0] * parsed.n_atoms,
            fixed_indices=[],
            energy=_safe_float(parsed.energies[index]),
            fmax=_safe_float(parsed.fmax[index]),
            symbols=parsed.symbols,
            numbers=parsed.numbers,
        )

    def _binary_payload(self, parsed: ParsedCclib, start: int, count: int) -> bytes:
        end = start + count
        positions = np.asarray(parsed.positions[start:end], dtype="<f4")
        cells = np.zeros((count, 3, 3), dtype="<f4")
        tags = np.zeros((count, parsed.n_atoms), dtype="<i4")
        fixed_mask = np.zeros((count, parsed.n_atoms), dtype=np.uint8)
        energy = _optional_float32(parsed.energies[start:end])
        fmax = _optional_float32(parsed.fmax[start:end])

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
            "n_frames_total": parsed.n_frames,
            "n_atoms": parsed.n_atoms,
            "topology_stable": True,
            "path": str(parsed.path),
            "name": parsed.name,
            "format": "cclib-output",
            "symbols": parsed.symbols,
            "numbers": parsed.numbers,
            "pbc": [False, False, False],
            "arrays": arrays,
            "nan_means_null": ["energy", "fmax"],
        }
        header_bytes = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header_padding = b"\0" * ((4 - (len(header_bytes) % 4)) % 4)
        return STRUCTURE_BINARY_MAGIC + struct.pack("<I", len(header_bytes)) + header_bytes + header_padding + b"".join(binary_parts)

    def _extract_fmax(self, data: Any, n_frames: int) -> list[float | None]:
        grads = getattr(data, "grads", None)
        if grads is None:
            return [None] * n_frames
        array = np.asarray(grads, dtype=np.float64)
        if array.ndim != 3 or array.shape[2] != 3:
            return [None] * n_frames
        magnitudes = np.linalg.norm(array * HARTREE_PER_BOHR_TO_EV_PER_ANGSTROM, axis=2)
        return _align_optional_values(np.max(magnitudes, axis=1), n_frames)

    @staticmethod
    def _metadata(data: Any) -> dict[str, Any]:
        metadata = getattr(data, "metadata", {}) or {}
        return {
            "parser": "cclib",
            "package": metadata.get("package"),
            "charge": getattr(data, "charge", None),
            "multiplicity": getattr(data, "mult", None),
            "success": metadata.get("success"),
            "fmax_units": "eV/angstrom",
        }


def create_plugin(context: Any) -> CclibPlugin:
    return CclibPlugin(context)


def _symbol(number: int) -> str:
    if 0 <= number < len(chemical_symbols) and chemical_symbols[number]:
        return chemical_symbols[number]
    return str(number)


def _zero_cell() -> list[list[float]]:
    return [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _align_optional_values(values: Any, n_frames: int) -> list[float | None]:
    if values is None:
        return [None] * n_frames
    items = [_safe_float(value) for value in np.asarray(values).reshape(-1).tolist()]
    if len(items) >= n_frames:
        return items[-n_frames:]
    return [None] * (n_frames - len(items)) + items


def _optional_float32(values: list[float | None]) -> np.ndarray:
    output = np.full((len(values),), np.nan, dtype="<f4")
    for index, value in enumerate(values):
        safe = _safe_float(value)
        if safe is not None:
            output[index] = safe
    return output
