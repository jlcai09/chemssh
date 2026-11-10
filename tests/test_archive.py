from pathlib import Path

from backend.app.services.archive_service import (
    archive_name,
    available_formats,
    compress_plan,
    extract_plan,
    extract_suffix_supported,
    temporary_tar_name,
)

ALL_TOOLS = {"tar": True, "zstd": True, "gzip": True, "xz": True}
TAR_ONLY = {"tar": True, "zstd": False, "gzip": False, "xz": False}


def test_available_formats_follow_installed_tools() -> None:
    assert available_formats(ALL_TOOLS) == ["tar.zst", "tar.gz", "tar.xz", "tar"]
    assert available_formats(TAR_ONLY) == ["tar"]
    assert available_formats({"tar": True, "zstd": True, "gzip": False, "xz": False}) == ["tar.zst", "tar"]
    assert available_formats({"tar": False, "zstd": True, "gzip": True, "xz": True}) == []


def test_archive_name_uses_archive_prefix_and_never_overwrites(tmp_path: Path) -> None:
    assert archive_name(tmp_path, "tar.gz") == "archive.tar.gz"

    (tmp_path / "archive.tar.gz").write_text("x", encoding="utf-8")
    assert archive_name(tmp_path, "tar.gz") == "archive_new.tar.gz"

    (tmp_path / "archive_new.tar.gz").write_text("x", encoding="utf-8")
    assert archive_name(tmp_path, "tar.gz") == "archive_new_new.tar.gz"

    # Other formats keep their own suffix.
    assert archive_name(tmp_path, "tar.zst") == "archive.tar.zst"


def test_compress_plans() -> None:
    plan = compress_plan("tar", "archive.tar", ["a.txt", "-b.txt"], "t0")
    assert [step.argv for step in plan.steps] == [["tar", "-cf", "archive.tar", "--", "a.txt", "-b.txt"]]
    assert plan.cleanup_paths() == []

    assert [step.argv for step in compress_plan("tar.gz", "archive.tar.gz", ["a"], "t0").steps] == [
        ["tar", "-czf", "archive.tar.gz", "--", "a"]
    ]
    assert [step.argv for step in compress_plan("tar.xz", "archive.tar.xz", ["a"], "t0").steps] == [
        ["tar", "-cJf", "archive.tar.xz", "--", "a"]
    ]


def test_tar_zst_compression_is_two_step_with_lowest_level() -> None:
    plan = compress_plan("tar.zst", "archive.tar.zst", ["a", "b"], "tok")
    temporary = temporary_tar_name("tok")
    assert [step.argv for step in plan.steps] == [
        ["tar", "-cf", temporary, "--", "a", "b"],
        ["zstd", "-1", "-f", temporary, "-o", "archive.tar.zst"],
    ]
    # The intermediate tarball is removed after the run.
    assert plan.cleanup_paths() == [temporary]


def test_extract_plans_cover_every_supported_suffix() -> None:
    def steps(name: str):
        plan = extract_plan(name, ALL_TOOLS, f"/tmp/{name}", "tok")
        assert plan is not None
        return [step.argv for step in plan.steps]

    assert steps("archive.tar.gz") == [["tar", "-xzf", "/tmp/archive.tar.gz"]]
    assert steps("archive.tgz") == [["tar", "-xzf", "/tmp/archive.tgz"]]
    assert steps("archive.tar.xz") == [["tar", "-xJf", "/tmp/archive.tar.xz"]]
    assert steps("archive.txz") == [["tar", "-xJf", "/tmp/archive.txz"]]
    assert steps("archive.tar") == [["tar", "-xf", "/tmp/archive.tar"]]
    assert steps("notes.txt.zst") == [["zstd", "-d", "-f", "/tmp/notes.txt.zst"]]
    assert steps("notes.txt.gz") == [["gzip", "-d", "-f", "/tmp/notes.txt.gz"]]
    assert steps("notes.txt.xz") == [["xz", "-d", "-f", "/tmp/notes.txt.xz"]]

    # Extensions are matched case-insensitively.
    assert extract_plan("ARCHIVE.TAR.GZ", ALL_TOOLS, "/tmp/ARCHIVE.TAR.GZ", "tok") is not None


def test_tar_zst_extraction_uses_a_temporary_tarball() -> None:
    plan = extract_plan("archive.tar.zst", ALL_TOOLS, "/data/archive.tar.zst", "tok")
    assert plan is not None
    temporary = temporary_tar_name("tok")
    assert [step.argv for step in plan.steps] == [
        ["zstd", "-d", "-f", "/data/archive.tar.zst", "-o", temporary],
        ["tar", "-xf", temporary],
    ]
    assert plan.cleanup_paths() == [temporary]


def test_extract_requires_the_matching_tool() -> None:
    assert extract_plan("archive.tar.zst", {"tar": True, "zstd": False}) is None
    assert extract_plan("notes.txt.zst", {"tar": True, "zstd": False}) is None
    assert extract_plan("archive.tar.xz", {"tar": True, "xz": False}) is None
    assert extract_plan("archive.tar", TAR_ONLY) is not None
    # Plain text and bare dotfiles are not archives.
    assert extract_plan("notes.txt", ALL_TOOLS) is None
    assert extract_plan(".gz", ALL_TOOLS) is None


def test_extract_suffix_detection_ignores_tool_availability() -> None:
    assert extract_suffix_supported("archive.tar.zst") is True
    assert extract_suffix_supported("notes.txt.gz") is True
    assert extract_suffix_supported("notes.txt") is False
