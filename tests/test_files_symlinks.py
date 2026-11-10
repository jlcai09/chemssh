from pathlib import Path

import os
import pytest

from backend.app.providers.filesystem.local_fs import LocalFileSystemProvider


def _make_symlink(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError) as exc:  # Windows without the privilege
        pytest.skip(f"symlinks are unavailable: {exc}")


def test_list_dir_marks_symlinks_and_keeps_dangling_ones(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "dir").mkdir()
    _make_symlink(tmp_path / "file.txt", tmp_path / "link-file")
    _make_symlink(tmp_path / "dir", tmp_path / "link-dir")
    _make_symlink(tmp_path / "missing", tmp_path / "link-broken")

    items = {item.name: item for item in LocalFileSystemProvider().list_dir(tmp_path).items}

    assert items["file.txt"].is_symlink is False
    assert items["file.txt"].link_target is None

    assert items["link-file"].type == "file"
    assert items["link-file"].is_symlink is True
    assert items["link-file"].link_broken is False
    assert items["link-file"].link_target == str(tmp_path / "file.txt")

    # A link to a directory stays enterable.
    assert items["link-dir"].type == "directory"
    assert items["link-dir"].is_symlink is True
    assert items["link-dir"].link_broken is False

    # A dangling link is listed instead of silently skipped.
    assert items["link-broken"].is_symlink is True
    assert items["link-broken"].link_broken is True
    assert items["link-broken"].size is None
    assert items["link-broken"].link_target == str(tmp_path / "missing")
