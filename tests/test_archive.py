from pathlib import Path

from backend.app.services.archive_service import (
    archive_name,
    archive_stem,
    available_formats,
    compress_plan,
    extract_plan,
    extract_suffix_supported,
    temporary_tar_name,
)

ALL_TOOLS = {"tar": True, "zstd": True, "gzip": True, "xz": True, "zip": True, "unzip": True, "7z": True}
TAR_ONLY = {"tar": True, "zstd": False, "gzip": False, "xz": False}


def test_available_formats_follow_installed_tools() -> None:
    assert available_formats(ALL_TOOLS) == ["tar.zst", "tar.gz", "tar.xz", "tar", "zip", "7z"]
    assert available_formats(TAR_ONLY) == ["tar"]
    assert available_formats({"tar": True, "zstd": True, "gzip": False, "xz": False}) == ["tar.zst", "tar"]
    assert available_formats({"tar": False, "zstd": True, "gzip": True, "xz": True}) == []
    # zip and 7z pack without tar; unzip alone cannot create anything.
    assert available_formats({"zip": True, "unzip": True, "7z": True}) == ["zip", "7z"]
    assert available_formats({"unzip": True}) == []


def test_archive_stem_uses_original_name_for_single_selection() -> None:
    assert archive_stem(["notes.txt"]) == "notes.txt"
    assert archive_stem(["data"]) == "data"
    assert archive_stem(["a.txt", "b.txt"]) == "archive"
    assert archive_stem([]) == "archive"


def test_archive_name_uses_selection_name_and_never_overwrites(tmp_path: Path) -> None:
    selection = ["a.txt", "sub"]
    assert archive_name(tmp_path, "tar.gz", selection) == "archive.tar.gz"

    (tmp_path / "archive.tar.gz").write_text("x", encoding="utf-8")
    assert archive_name(tmp_path, "tar.gz", selection) == "archive_new.tar.gz"

    (tmp_path / "archive_new.tar.gz").write_text("x", encoding="utf-8")
    assert archive_name(tmp_path, "tar.gz", selection) == "archive_new_new.tar.gz"

    # Other formats keep their own suffix.
    assert archive_name(tmp_path, "tar.zst", selection) == "archive.tar.zst"


def test_archive_name_uses_original_name_for_single_selection(tmp_path: Path) -> None:
    assert archive_name(tmp_path, "tar.gz", ["notes.txt"]) == "notes.txt.tar.gz"

    (tmp_path / "notes.txt.tar.gz").write_text("x", encoding="utf-8")
    assert archive_name(tmp_path, "tar.gz", ["notes.txt"]) == "notes.txt_new.tar.gz"

    # A single folder also keeps its name.
    assert archive_name(tmp_path, "tar", ["data"]) == "data.tar"


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
    assert [step.argv for step in compress_plan("zip", "archive.zip", ["a.txt", "-b.txt"], "t0").steps] == [
        ["zip", "-r", "archive.zip", "--", "a.txt", "-b.txt"]
    ]
    assert [step.argv for step in compress_plan("7z", "archive.7z", ["a", "sub"], "t0").steps] == [
        ["7z", "a", "-y", "archive.7z", "--", "a", "sub"]
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
    assert steps("archive.zip") == [["unzip", "-o", "/tmp/archive.zip"]]
    assert steps("archive.7z") == [["7z", "x", "-y", "/tmp/archive.7z"]]

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
    # zip extraction needs unzip, not the zip packer; 7z needs 7z.
    assert extract_plan("archive.zip", {"zip": True}) is None
    assert extract_plan("archive.zip", {"unzip": True}) is not None
    assert extract_plan("archive.7z", {"zip": True, "unzip": True}) is None
    assert extract_plan("archive.7z", {"7z": True}) is not None
    # Plain text and bare dotfiles are not archives.
    assert extract_plan("notes.txt", ALL_TOOLS) is None
    assert extract_plan(".gz", ALL_TOOLS) is None


def test_extract_suffix_detection_ignores_tool_availability() -> None:
    assert extract_suffix_supported("archive.tar.zst") is True
    assert extract_suffix_supported("notes.txt.gz") is True
    assert extract_suffix_supported("archive.zip") is True
    assert extract_suffix_supported("ARCHIVE.7Z") is True
    assert extract_suffix_supported("notes.txt") is False
