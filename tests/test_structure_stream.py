from __future__ import annotations

import asyncio
import base64
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.api.structures import stream_ase_frames
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.structure_service import StructureService


def stream_client(root: Path, chunk_limit: int = 32) -> TestClient:
    settings = Settings(
        workspace={"root": root},
        viewer={"ase": {"binary_chunk_frames": chunk_limit}},
        server={"debug": True},
        client_cache={"enabled": False},
    )
    return TestClient(create_app(settings))


def write_movie(path: Path, frames: int) -> None:
    path.write_text("".join(f"1\nframe {index}\nH {index} 0 0\n" for index in range(frames)), encoding="utf-8")


def parse_events(text: str) -> list[tuple[str, str]]:
    return [(lines[0][7:], lines[1][6:]) for event in text.strip().split("\n\n") if (lines := event.splitlines())]


def decode_chunk(data: str) -> tuple[dict, np.ndarray]:
    payload = base64.b64decode(data)
    header_size = struct.unpack_from("<I", payload, 4)[0]
    header = json.loads(payload[8:8 + header_size])
    body_start = (8 + header_size + 3) // 4 * 4
    positions = header["arrays"]["positions"]
    values = np.frombuffer(payload, dtype="<f4", count=positions["byte_length"] // 4, offset=body_start + positions["offset"])
    return header, values.reshape(positions["shape"])


@pytest.mark.parametrize(("requested", "limit"), [(1, 32), (16, 32), (32, 32), (64, 32), (512, 3)])
def test_stream_covers_every_frame(tmp_path: Path, requested: int, limit: int) -> None:
    sample = tmp_path / "movie.xyz"
    write_movie(sample, 130)
    response = stream_client(tmp_path, limit).get(
        "/api/structures/ase/frames.stream", params={"path": str(sample), "chunk": requested},
    )
    assert response.status_code == 200
    events = parse_events(response.text)
    assert events[-1] == ("done", '{"n_frames": 130}')
    assert not any(name == "error" for name, _ in events)
    next_frame = 0
    metas = []
    for name, data in events:
        if name == "meta":
            metas.append(json.loads(data))
        if name != "chunk":
            continue
        header, positions = decode_chunk(data)
        assert header["start"] == next_frame
        assert 0 < header["count"] <= min(requested, limit)
        assert metas[-1]["count"] == header["count"]
        assert positions[:, 0, 0].tolist() == list(range(next_frame, next_frame + header["count"]))
        next_frame += header["count"]
    assert next_frame == 130


def test_stream_advances_by_returned_count(tmp_path: Path, monkeypatch) -> None:
    sample = tmp_path / "movie.xyz"
    write_movie(sample, 9)
    original = StructureService.stream_frame_chunk_binary

    def shorter(self, path, start, count, fmt, summary, profile=None):
        return original(self, path, start, min(count, 2), fmt, summary, profile)

    monkeypatch.setattr(StructureService, "stream_frame_chunk_binary", shorter)
    response = stream_client(tmp_path).get("/api/structures/ase/frames.stream", params={"path": str(sample)})
    chunks = [decode_chunk(data)[0] for name, data in parse_events(response.text) if name == "chunk"]
    assert [(chunk["start"], chunk["count"]) for chunk in chunks] == [(0, 2), (2, 2), (4, 2), (6, 2), (8, 1)]


@pytest.mark.parametrize("failure", ["exception", "empty", "wrong_start"])
def test_stream_failure_never_sends_done(tmp_path: Path, monkeypatch, failure: str) -> None:
    sample = tmp_path / "movie.xyz"
    write_movie(sample, 5)
    original = StructureService.stream_frame_chunk_binary

    def failing(self, path, start, count, fmt, summary, profile=None):
        if start == 0:
            return original(self, path, start, count, fmt, summary, profile)
        if failure == "exception":
            raise RuntimeError("injected pack failure")
        header = json.dumps({"start": start + (failure == "wrong_start"), "count": 0 if failure == "empty" else 1}).encode()
        return b"CWB1" + struct.pack("<I", len(header)) + header

    monkeypatch.setattr(StructureService, "stream_frame_chunk_binary", failing)
    response = stream_client(tmp_path, 2).get("/api/structures/ase/frames.stream", params={"path": str(sample)})
    names = [name for name, _ in parse_events(response.text)]
    assert names.count("chunk") == 1
    assert names[-1] == "error"
    assert "done" not in names


def test_closing_stream_cancels_token_and_watcher() -> None:
    async def run() -> None:
        tokens = []
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

        async def connected():
            return False

        def summary(path, fmt, cancellation, **kwargs):
            tokens.append(cancellation)
            return SimpleNamespace(n_frames=2, scan_completed=True)

        def pack(path, start, count, fmt, summary, **kwargs):
            header = json.dumps({"start": start, "count": 1}).encode()
            return b"CWB1" + struct.pack("<I", len(header)) + header

        request.is_disconnected = connected
        service = SimpleNamespace(
            _resolve_structure_file=lambda *args, **kwargs: Path("synthetic.xyz"),
            stream_requires_complete_summary=lambda *args: False,
            _get_structure_summary=summary,
            frame_chunk_count=lambda *args: 1,
            stream_frame_chunk_binary=pack,
        )
        before = set(asyncio.all_tasks())
        response = await stream_ase_frames(request, "synthetic.xyz", None, False, 1, service)
        first = await anext(response.body_iterator)
        assert first.startswith("event: chunk")
        await response.body_iterator.aclose()
        assert tokens[0]._event.is_set()
        assert set(asyncio.all_tasks()) == before

    asyncio.run(run())
