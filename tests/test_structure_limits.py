from __future__ import annotations

import json
import struct
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from ase import Atoms
from pydantic import ValidationError

from backend.app.core.config import AseViewerConfig, Settings, ViewerConfig, WorkspaceConfig
from backend.app.core.errors import AppError
import backend.app.services.structure_service as structure_service_module
from backend.app.services.structure_service import StructureService, StructureSummary


def _service(root: Path, **config: int) -> StructureService:
    return StructureService(Settings(
        workspace=WorkspaceConfig(root=root),
        viewer=ViewerConfig(ase=AseViewerConfig(**config)),
    ))


def _summary(n_atoms: int, *, topology_stable: bool = True, n_frames: int = 100) -> StructureSummary:
    return StructureSummary(
        n_frames=n_frames,
        n_atoms=n_atoms,
        last_atoms=None,
        topology_stable=topology_stable,
        detected_format="xyz",
    )


def _write_xyz(path: Path, atom_counts: list[int]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index, n_atoms in enumerate(atom_counts):
            handle.write(f"{n_atoms}\nframe {index}\n")
            handle.write(f"H {index} 0 0\n" * n_atoms)


def _decode_binary(payload: bytes) -> tuple[dict, np.ndarray]:
    assert payload[:4] == b"CWB1"
    header_size = struct.unpack("<I", payload[4:8])[0]
    header = json.loads(payload[8:8 + header_size].decode("utf-8"))
    assert header["dtype"] == "float32-le"
    assert header["int_dtype"] == "int32-le"
    data_start = 8 + header_size + (-header_size % 4)
    positions = header["arrays"]["positions"]
    array = np.frombuffer(
        payload,
        dtype="<f4",
        offset=data_start + positions["offset"],
        count=positions["byte_length"] // 4,
    ).reshape(positions["shape"])
    return header, array


def test_chunk_budget_config_default_and_bounds() -> None:
    assert AseViewerConfig().max_chunk_size_mb == 8
    for value in (1, 64):
        assert AseViewerConfig(max_chunk_size_mb=value).max_chunk_size_mb == value
    for value in (0, 65):
        with pytest.raises(ValidationError):
            AseViewerConfig(max_chunk_size_mb=value)


@pytest.mark.parametrize("json_transport, expected", [(False, 32), (True, 4)])
def test_fixed_chunk_count_uses_atom_estimate(tmp_path: Path, json_transport: bool, expected: int) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1, binary_chunk_frames=64)
    summary = _summary(1_000)
    assert service.frame_chunk_count(summary, 100, json_transport=json_transport) == expected
    assert service.frame_chunk_count(summary, 2, json_transport=json_transport) == 2
    service.settings.viewer.ase.binary_chunk_frames = 3
    assert service.frame_chunk_count(summary, 100, json_transport=json_transport) == 3


@pytest.mark.parametrize("json_transport, expected", [(False, 3), (True, 1)])
@pytest.mark.parametrize("has_summary", [False, True])
def test_unknown_or_variable_topology_uses_max_atoms(
    tmp_path: Path, json_transport: bool, expected: int, has_summary: bool,
) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1, max_atoms=10_000)
    summary = _summary(1, topology_stable=False) if has_summary else None
    assert service.frame_chunk_count(summary, 32, json_transport=json_transport) == expected


def test_budget_upper_limit_and_default_large_frame(tmp_path: Path) -> None:
    service = _service(tmp_path)
    summary = _summary(200_000)
    assert 200_000 * 32 + 256 < 8 * 1024 * 1024
    assert service.frame_chunk_count(summary, 32) == 1
    service.settings.viewer.ase.max_chunk_size_mb = 64
    assert service.frame_chunk_count(summary, 32) == 10
    assert service.frame_chunk_count(_summary(1), 512) == 32


@pytest.mark.parametrize("json_transport", [False, True])
def test_single_frame_exception_keeps_large_trajectories_readable(tmp_path: Path, json_transport: bool) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1)
    for summary in (_summary(200_000), _summary(1, topology_stable=False), None):
        assert service.frame_chunk_count(summary, 32, json_transport=json_transport) == 1
    assert service.frame_chunk_count(_summary(1), 0, json_transport=json_transport) == 1


@pytest.mark.parametrize("transport", ["json", "binary", "stream"])
def test_oversized_fixed_summary_is_rejected_before_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: str,
) -> None:
    service = _service(tmp_path, max_atoms=100)
    path = tmp_path / "cached.xyz"
    _write_xyz(path, [1])
    summary = _summary(101)
    monkeypatch.setattr(service, "_get_structure_summary", lambda *args, **kwargs: summary)
    monkeypatch.setattr(service, "_get_reusable_summary_if_supported", lambda *args, **kwargs: summary)
    direct = Mock(side_effect=AssertionError("must validate before direct allocation"))
    read_range = Mock(side_effect=AssertionError("must validate before range allocation"))
    monkeypatch.setattr(service, "_try_build_direct_fixed_binary_payload", direct)
    monkeypatch.setattr(service, "_read_frame_range", read_range)
    with pytest.raises(AppError) as error:
        if transport == "stream":
            service.stream_frame_chunk_binary(path, 0, 32, None, summary)
        elif transport == "binary":
            service.read_frame_chunk_binary(str(path), 0, 32)
        else:
            service.read_frame_chunk_json(str(path), 0, 32)
    assert error.value.code == "STRUCTURE_TOO_MANY_ATOMS"
    assert error.value.status_code == 413
    direct.assert_not_called()
    read_range.assert_not_called()


@pytest.mark.parametrize("transport, fallback", [
    ("json", False), ("binary", False), ("binary", True), ("stream", False), ("stream", True),
])
def test_real_xyz_budget_and_tail_can_be_read_using_returned_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: str, fallback: bool,
) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1)
    path = tmp_path / "movie.xyz"
    _write_xyz(path, [2_000] * 19)
    summary = service._get_structure_summary(path, None, allow_incomplete=False)
    if fallback:
        monkeypatch.setattr(service, "_try_build_direct_fixed_binary_payload", lambda **kwargs: None)
    elif transport != "json":
        monkeypatch.setattr(service, "_read_frame_range", Mock(side_effect=AssertionError("keep direct fast path")))

    start = 0
    counts = []
    visited = []
    while start < summary.n_frames:
        if transport == "json":
            chunk = service.read_frame_chunk_json(str(path), start, 32)
            assert chunk.start == start
            count = chunk.count
            assert len(chunk.frames) == count
            assert [frame.frame_index for frame in chunk.frames] == list(range(start, start + count))
            visited.extend(frame.positions[0][0] for frame in chunk.frames)
        else:
            profile = {}
            payload = (
                service.stream_frame_chunk_binary(path, start, 32, None, summary, profile)
                if transport == "stream" else service.read_frame_chunk_binary(str(path), start, 32)
            )
            header, positions = _decode_binary(payload)
            assert header["start"] == start
            assert header["n_frames_total"] == 19
            count = header["count"]
            assert positions.shape == (count, 2_000, 3)
            assert len(payload) < 1024 * 1024
            if transport == "stream":
                assert profile["safe_count"] == count
            visited.extend(positions[:, 0, 0].tolist())
        assert 0 < count < 32
        counts.append(count)
        start += count

    assert visited == list(range(19))
    assert counts == ([2] * 9 + [1] if transport == "json" else [16, 3])


@pytest.mark.parametrize("transport", ["json", "binary", "stream"])
def test_real_variable_xyz_uses_conservative_count(tmp_path: Path, transport: str) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1, max_atoms=10_000)
    path = tmp_path / "variable.xyz"
    atom_counts = [1, 2, 1, 2, 1, 2, 1]
    _write_xyz(path, atom_counts)
    summary = service._get_structure_summary(path, None, allow_incomplete=False)
    assert not summary.topology_stable
    start = 0
    returned = []
    while start < len(atom_counts):
        if transport == "json":
            chunk = service.read_frame_chunk_json(str(path), start, 32)
            count = chunk.count
            assert count == 1
            assert len(chunk.frames[0].positions) == atom_counts[start]
            assert chunk.frames[0].positions[0][0] == start
        else:
            payload = (
                service.stream_frame_chunk_binary(path, start, 32, None, summary)
                if transport == "stream" else service.read_frame_chunk_binary(str(path), start, 32)
            )
            header, positions = _decode_binary(payload)
            count = header["count"]
            assert count == min(3, len(atom_counts) - start)
            if count > 1:
                assert header["frame_encoding"] == "variable-atoms-v1"
                assert positions[:, 0].tolist() == [
                    index for index in range(start, start + count) for _ in range(atom_counts[index])
                ]
            else:
                assert positions[0, 0, 0] == start
        returned.extend(range(start, start + count))
        start += count
    assert returned == list(range(len(atom_counts)))


def test_json_without_summary_reads_real_xyz_conservatively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1, max_atoms=2_000)
    path = tmp_path / "no-summary.xyz"
    _write_xyz(path, [2] * 5)
    monkeypatch.setattr(service, "_get_reusable_summary_if_supported", lambda *args, **kwargs: None)
    start = 0
    counts = []
    visited = []
    while start < 5:
        chunk = service.read_frame_chunk_json(str(path), start, 32, "xyz")
        assert 0 < chunk.count <= 2
        counts.append(chunk.count)
        visited.extend(frame.positions[0][0] for frame in chunk.frames)
        start += chunk.count
    assert counts == [2, 2, 1]
    assert visited == list(range(5))


@pytest.mark.parametrize("fallback", [False, True])
def test_ase_iterator_does_not_read_past_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fallback: bool,
) -> None:
    service = _service(tmp_path, max_chunk_size_mb=1, max_atoms=2_000)
    path = tmp_path / "iterator.xyz"
    _write_xyz(path, [1] * 5)
    monkeypatch.setattr(service, "_get_reusable_summary_if_supported", lambda *args, **kwargs: None)
    consumed = []

    def fake_iread(*args, index, **kwargs):
        if fallback and isinstance(index, slice):
            raise ValueError("slice unsupported")
        first = 0 if index == ":" else index.start
        for frame_index in range(first, 100):
            consumed.append(frame_index)
            yield Atoms("H", positions=[[frame_index, 0, 0]])

    monkeypatch.setattr(structure_service_module, "iread", fake_iread)
    chunk = service.read_frame_chunk_json(str(path), 1, 32)
    assert chunk.count == 2
    assert [frame.positions[0][0] for frame in chunk.frames] == [1, 2]
    assert consumed == ([0, 1, 2] if fallback else [1, 2])
