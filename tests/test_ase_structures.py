from __future__ import annotations

import json
import struct
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from ase import Atoms
from ase.calculators.singlepoint import SinglePointCalculator
from ase.constraints import FixAtoms
from ase.db import connect
from ase.io import write
from fastapi.testclient import TestClient

from backend.app.core.config import (
    AseViewerConfig,
    BrotliConfig,
    CompressionConfig,
    Settings,
    ViewerConfig,
    WorkspaceConfig,
)
from backend.app.main import create_app
from backend.app.services.structure_service import STRUCTURE_BINARY_MEDIA_TYPE


def make_client(
    root: Path,
    *,
    max_points_json: int = 200_000,
    max_file_size_mb: int = 50,
) -> TestClient:
    settings = Settings(
        workspace=WorkspaceConfig(root=root),
        viewer=ViewerConfig(max_file_size_mb=max_file_size_mb, ase=AseViewerConfig(max_points_json=max_points_json)),
    )
    return TestClient(create_app(settings))


def make_compressed_client(root: Path, *, max_points_json: int = 1) -> TestClient:
    settings = Settings(
        workspace=WorkspaceConfig(root=root),
        viewer=ViewerConfig(ase=AseViewerConfig(max_points_json=max_points_json)),
        compression=CompressionConfig(brotli=BrotliConfig(enabled=True, level=1)),
    )
    return TestClient(create_app(settings))


def test_ase_preview_reads_xyz(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "water.xyz"
    sample.write_text("3\nwater\nO 0 0 0\nH 0.76 0.58 0\nH -0.76 0.58 0\n", encoding="utf-8")

    response = client.get("/api/structures/ase/preview", params={"path": str(sample)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "water.xyz"
    assert payload["transport"] == "json"
    assert payload["is_trajectory"] is False
    assert payload["n_frames"] == 1
    assert payload["n_atoms"] == 3
    assert payload["initial_frame_index"] == 0
    assert payload["frame"]["symbols"] == ["O", "H", "H"]
    assert payload["frame"]["positions"][1] == [0.76, 0.58, 0.0]


def test_ase_preview_returns_last_trajectory_frame_and_fixed_indices(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "fixed.traj"
    frame0 = Atoms("H2", positions=[[0, 0, 0], [0, 0, 1]])
    frame1 = Atoms("H2", positions=[[0, 0, 0], [0, 0, 2]])
    for atoms in (frame0, frame1):
        atoms.set_constraint(FixAtoms(indices=[1]))
    frame0.calc = SinglePointCalculator(frame0, energy=-1.0, forces=np.array([[1, 0, 0], [0, 0, 50]]))
    frame1.calc = SinglePointCalculator(frame1, energy=-2.0, forces=np.array([[0, 2, 0], [0, 0, 99]]))
    write(sample, [frame0, frame1])

    response = client.get("/api/structures/ase/preview", params={"path": str(sample)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_trajectory"] is True
    assert payload["transport"] == "binary-available"
    assert payload["n_frames"] == 2
    assert payload["initial_frame_index"] == 1
    assert payload["frame"]["positions"][1] == [0.0, 0.0, 2.0]
    assert payload["frame"]["fixed_indices"] == [1]
    assert payload["frame"]["energy"] == -2.0
    assert payload["frame"]["fmax"] == 2.0


def test_ase_frame_reads_requested_index(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "movie.xyz"
    sample.write_text(
        "1\nframe 0\nH 0 0 0\n"
        "1\nframe 1\nH 1 0 0\n",
        encoding="utf-8",
    )

    response = client.get("/api/structures/ase/frame", params={"path": str(sample), "index": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["frame_index"] == 1
    assert payload["positions"] == [[1.0, 0.0, 0.0]]


def test_ase_preview_and_json_chunk_support_variable_topology_db(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "mixed.db"
    database = connect(sample)
    database.write(Atoms("H", positions=[[0, 0, 0]]))
    database.write(Atoms("H2", positions=[[0, 0, 0], [0, 0, 1]]))
    database.write(Atoms("O", positions=[[1, 0, 0]]))

    preview = client.get("/api/structures/ase/preview", params={"path": str(sample)})
    chunk = client.get("/api/structures/ase/frames", params={"path": str(sample), "start": 0, "count": 3})

    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["is_trajectory"] is True
    assert preview_payload["topology_stable"] is False
    assert preview_payload["transport"] == "json"
    assert preview_payload["n_frames"] == 3

    assert chunk.status_code == 200
    chunk_payload = chunk.json()
    assert chunk_payload["start"] == 0
    assert chunk_payload["count"] == 3
    assert [frame["symbols"] for frame in chunk_payload["frames"]] == [["H"], ["H", "H"], ["O"]]


def test_ase_preview_blocks_path_traversal(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/structures/ase/preview", params={"path": str(tmp_path / ".." / "outside.xyz")})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_PATH"


def test_ase_parse_failure_uses_app_error(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "bad.xyz"
    sample.write_text("not an xyz file\n", encoding="utf-8")

    response = client.get("/api/structures/ase/preview", params={"path": str(sample)})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "STRUCTURE_PARSE_FAILED"


def test_ase_preview_and_frames_can_force_large_file(tmp_path: Path) -> None:
    client = make_client(tmp_path, max_file_size_mb=0)
    sample = tmp_path / "movie.xyz"
    sample.write_text(
        "1\nframe 0\nH 0 0 0\n"
        "1\nframe 1\nH 1 0 0\n",
        encoding="utf-8",
    )

    blocked = client.get("/api/structures/ase/preview", params={"path": str(sample)})
    forced_preview = client.get("/api/structures/ase/preview", params={"path": str(sample), "force": True})
    forced_frame = client.get("/api/structures/ase/frame", params={"path": str(sample), "index": 1, "force": True})
    forced_chunk = client.get(
        "/api/structures/ase/frames.bin",
        params={"path": str(sample), "start": 0, "count": 2, "force": True},
    )

    assert blocked.status_code == 413
    assert blocked.json()["error"]["code"] == "STRUCTURE_FILE_TOO_LARGE"
    assert forced_preview.status_code == 200
    assert forced_preview.json()["size_limit_overridden"] is True
    assert forced_frame.status_code == 200
    assert forced_frame.json()["positions"] == [[1.0, 0.0, 0.0]]
    assert forced_chunk.status_code == 200
    assert forced_chunk.content[:4] == b"CWB1"


def test_ase_binary_envelope_contains_float32_positions_and_fixed_mask(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    sample = tmp_path / "fixed.traj"
    frame0 = Atoms("H2", positions=[[0, 0, 0], [0, 0, 1]])
    frame1 = Atoms("H2", positions=[[1, 0, 0], [1, 0, 1]])
    for atoms in (frame0, frame1):
        atoms.set_constraint(FixAtoms(indices=[1]))
    write(sample, [frame0, frame1])

    response = client.get("/api/structures/ase/frames.bin", params={"path": str(sample), "start": 0, "count": 2})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(STRUCTURE_BINARY_MEDIA_TYPE)
    body = response.content
    assert body[:4] == b"CWB1"
    header_len = struct.unpack("<I", body[4:8])[0]
    header = json.loads(body[8 : 8 + header_len].decode("utf-8"))
    padding = (4 - (header_len % 4)) % 4
    data_start = 8 + header_len + padding

    assert header["arrays"]["positions"]["shape"] == [2, 2, 3]
    assert header["arrays"]["fixed_mask"]["shape"] == [2, 2]

    positions_spec = header["arrays"]["positions"]
    positions = np.frombuffer(
        body,
        dtype="<f4",
        count=positions_spec["byte_length"] // np.dtype("<f4").itemsize,
        offset=data_start + positions_spec["offset"],
    ).reshape(positions_spec["shape"])
    assert positions[1, 0].tolist() == [1.0, 0.0, 0.0]

    fixed_spec = header["arrays"]["fixed_mask"]
    fixed_mask = np.frombuffer(
        body,
        dtype=np.uint8,
        count=fixed_spec["byte_length"],
        offset=data_start + fixed_spec["offset"],
    ).reshape(fixed_spec["shape"])
    assert fixed_mask.tolist() == [[0, 1], [0, 1]]


def test_brotli_compresses_ase_json_and_binary_but_not_zip(tmp_path: Path) -> None:
    client = make_compressed_client(tmp_path, max_points_json=200_000)
    sample = tmp_path / "movie.xyz"
    sample.write_text(
        "1\nframe 0\nH 0 0 0\n"
        "1\nframe 1\nH 1 0 0\n",
        encoding="utf-8",
    )

    json_response = client.get(
        "/api/structures/ase/preview",
        params={"path": str(sample)},
        headers={"Accept-Encoding": "br"},
    )
    assert json_response.status_code == 200
    assert json_response.headers["content-encoding"] == "br"
    assert json_response.json()["transport"] == "binary-available"

    binary_response = client.get(
        "/api/structures/ase/frames.bin",
        params={"path": str(sample), "start": 0, "count": 2},
        headers={"Accept-Encoding": "br"},
    )
    assert binary_response.status_code == 200
    assert binary_response.headers["content-encoding"] == "br"
    assert binary_response.content[:4] == b"CWB1"

    zip_response = client.post(
        "/api/files/download-archive",
        json={"paths": [str(sample)]},
        headers={"Accept-Encoding": "br"},
    )
    assert zip_response.status_code == 200
    assert "content-encoding" not in zip_response.headers
    with ZipFile(BytesIO(zip_response.content)) as archive:
        assert "movie.xyz" in archive.namelist()
