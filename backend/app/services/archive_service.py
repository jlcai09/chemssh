from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Archive created next to the selected entries. A single entry keeps its own
# name; several entries share this placeholder. `_new` keeps being appended so
# an existing file is never overwritten.
ARCHIVE_PREFIX = "archive"
ARCHIVE_NEW_STEM = "_new"

FORMAT_SUFFIXES: dict[str, str] = {
    "tar.zst": ".tar.zst",
    "tar.gz": ".tar.gz",
    "tar.xz": ".tar.xz",
    "tar": ".tar",
    "zip": ".zip",
    "7z": ".7z",
}

# Every tar format needs tar to bundle files and folders together; the
# compressor is what actually shrinks the tarball. zip and 7z pack on their own.
FORMAT_TOOLS: dict[str, tuple[str, ...]] = {
    "tar.zst": ("tar", "zstd"),
    "tar.gz": ("tar", "gzip"),
    "tar.xz": ("tar", "xz"),
    "tar": ("tar",),
    "zip": ("zip",),
    "7z": ("7z",),
}

PROBE_TOOLS = ("tar", "zstd", "gzip", "xz", "zip", "unzip", "7z")

# Longest suffixes first: `.tar.gz` must win over `.gz`.
EXTRACT_SUFFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (".tar.zst", ("tar", "zstd")),
    (".tzst", ("tar", "zstd")),
    (".tar.gz", ("tar", "gzip")),
    (".tgz", ("tar", "gzip")),
    (".tar.xz", ("tar", "xz")),
    (".txz", ("tar", "xz")),
    (".tar", ("tar",)),
    (".zst", ("zstd",)),
    (".gz", ("gzip",)),
    (".xz", ("xz",)),
    (".zip", ("unzip",)),
    (".7z", ("7z",)),
)

ZSTD_LEVEL = "-1"


@dataclass(frozen=True)
class ArchiveStep:
    """One command of a plan; `cleanup` is a file the step creates and leaves behind."""

    argv: list[str]
    cleanup: str | None = None


@dataclass(frozen=True)
class ArchivePlan:
    steps: list[ArchiveStep]

    def cleanup_paths(self) -> list[str]:
        return [step.cleanup for step in self.steps if step.cleanup]


def probe_tools() -> dict[str, bool]:
    return {name: shutil.which(name) is not None for name in PROBE_TOOLS}


def available_formats(tools: dict[str, bool]) -> list[str]:
    return [fmt for fmt, needed in FORMAT_TOOLS.items() if all(tools.get(tool) for tool in needed)]


def archive_stem(names: list[str]) -> str:
    """Base name for a generated archive.

    Compressing a single entry keeps its original name so the result is
    recognizable; bundling several entries falls back to the placeholder.
    """
    if len(names) == 1 and names[0]:
        return names[0]
    return ARCHIVE_PREFIX


def archive_name(directory: Path, fmt: str, names: list[str]) -> str:
    suffix = FORMAT_SUFFIXES.get(fmt)
    if suffix is None:
        raise KeyError(fmt)
    stem = archive_stem(names)
    while (directory / f"{stem}{suffix}").exists():
        stem += ARCHIVE_NEW_STEM
    return f"{stem}{suffix}"


def temporary_tar_name(token: str) -> str:
    return f".chemssh-archive-{token}.tar"


def compress_plan(fmt: str, archive: str, names: list[str], token: str) -> ArchivePlan:
    if fmt == "tar.zst":
        # zstd is driven directly instead of through `tar --use-compress-program`:
        # bsdtar does not pass `-d` when extracting, GNU tar does, and the
        # two-step form behaves the same on both. -1 is zstd's cheapest level.
        temporary = temporary_tar_name(token)
        return ArchivePlan(
            steps=[
                ArchiveStep(["tar", "-cf", temporary, "--", *names]),
                ArchiveStep(["zstd", ZSTD_LEVEL, "-f", temporary, "-o", archive], cleanup=temporary),
            ]
        )
    if fmt == "tar.gz":
        return ArchivePlan([ArchiveStep(["tar", "-czf", archive, "--", *names])])
    if fmt == "tar.xz":
        return ArchivePlan([ArchiveStep(["tar", "-cJf", archive, "--", *names])])
    if fmt == "tar":
        return ArchivePlan([ArchiveStep(["tar", "-cf", archive, "--", *names])])
    if fmt == "zip":
        return ArchivePlan([ArchiveStep(["zip", "-r", archive, "--", *names])])
    if fmt == "7z":
        return ArchivePlan([ArchiveStep(["7z", "a", "-y", archive, "--", *names])])
    raise KeyError(fmt)


def extract_plan(
    name: str,
    tools: dict[str, bool],
    archive_argument: str | None = None,
    token: str = "tmp",
) -> ArchivePlan | None:
    """Build the extraction plan for `name`.

    `archive_argument` is what the tool receives and may be an absolute path when
    the archive is not extracted inside its own directory; `name` only drives the
    suffix detection.
    """
    argument = archive_argument or name
    lower = name.lower()
    for suffix, needed in EXTRACT_SUFFIXES:
        if not lower.endswith(suffix) or len(lower) == len(suffix):
            continue
        if not all(tools.get(tool) for tool in needed):
            return None
        if suffix in (".tar.zst", ".tzst"):
            temporary = temporary_tar_name(token)
            return ArchivePlan(
                steps=[
                    ArchiveStep(["zstd", "-d", "-f", argument, "-o", temporary], cleanup=temporary),
                    ArchiveStep(["tar", "-xf", temporary]),
                ]
            )
        if suffix in (".tar.gz", ".tgz"):
            return ArchivePlan([ArchiveStep(["tar", "-xzf", argument])])
        if suffix in (".tar.xz", ".txz"):
            return ArchivePlan([ArchiveStep(["tar", "-xJf", argument])])
        if suffix == ".tar":
            return ArchivePlan([ArchiveStep(["tar", "-xf", argument])])
        if suffix == ".zst":
            return ArchivePlan([ArchiveStep(["zstd", "-d", "-f", argument])])
        if suffix == ".gz":
            return ArchivePlan([ArchiveStep(["gzip", "-d", "-f", argument])])
        if suffix == ".xz":
            return ArchivePlan([ArchiveStep(["xz", "-d", "-f", argument])])
        if suffix == ".zip":
            return ArchivePlan([ArchiveStep(["unzip", "-o", argument])])
        if suffix == ".7z":
            return ArchivePlan([ArchiveStep(["7z", "x", "-y", argument])])
    return None


def extract_suffix_supported(name: str) -> bool:
    """True when the name looks like an archive, regardless of installed tools."""
    lower = name.lower()
    return any(lower.endswith(suffix) and len(lower) > len(suffix) for suffix, _ in EXTRACT_SUFFIXES)
