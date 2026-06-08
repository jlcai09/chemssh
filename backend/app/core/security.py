from __future__ import annotations

import re
from pathlib import Path

from .errors import AppError


SCRIPT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{2}[^\\/])")


class WorkspaceSecurity:
    def __init__(self, root: str | Path) -> None:
        raw_root = str(root)
        self.root_platform = _absolute_path_platform(raw_root)
        self.root = Path(raw_root).expanduser().resolve()
        self.root_platform = self.root_platform or _absolute_path_platform(str(self.root))

    def resolve_path(self, raw_path: str | Path | None = None) -> Path:
        if raw_path is None or str(raw_path).strip() == "":
            return self.root

        raw_value = str(raw_path).strip()
        path_platform = _absolute_path_platform(raw_value)
        if path_platform and self.root_platform and path_platform != self.root_platform:
            raise AppError(
                "INVALID_PATH_PLATFORM",
                f"Path platform does not match workspace root: {raw_path}",
                status_code=400,
            )

        path = Path(raw_value).expanduser()
        candidate = path if path.is_absolute() else self.root / path
        resolved = candidate.resolve(strict=False)
        if not self.is_allowed(resolved):
            raise AppError(
                "FORBIDDEN_PATH",
                f"Path is outside workspace root: {raw_path}",
                status_code=403,
            )
        return resolved

    def is_allowed(self, path: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(self.root)
            return True
        except ValueError:
            return False

    def validate_child_name(self, name: str, *, field: str = "name") -> str:
        if not name or Path(name).name != name:
            raise AppError("INVALID_NAME", f"Invalid {field}: {name}", status_code=400)
        if not SCRIPT_NAME_RE.match(name):
            raise AppError(
                "INVALID_NAME",
                f"{field} may contain only letters, numbers, dot, underscore and dash",
                status_code=400,
            )
        return name

    def resolve_child(self, directory: str | Path, name: str, *, field: str = "name") -> Path:
        base = self.resolve_path(directory)
        safe_name = self.validate_child_name(name, field=field)
        child = (base / safe_name).resolve(strict=False)
        if not self.is_allowed(child):
            raise AppError("FORBIDDEN_PATH", f"Path is outside workspace root: {name}", 403)
        return child


def validate_script_name(script: str) -> str:
    if not script or Path(script).name != script:
        raise AppError("INVALID_SCRIPT", "script must be a file name, not a path", 400)
    if not SCRIPT_NAME_RE.match(script):
        raise AppError(
            "INVALID_SCRIPT",
            "script may contain only letters, numbers, dot, underscore and dash",
            400,
        )
    return script


def validate_job_id(job_id: str) -> str:
    if not job_id or not JOB_ID_RE.match(job_id):
        raise AppError("INVALID_JOB_ID", f"Invalid job id: {job_id}", 400)
    return job_id


def _absolute_path_platform(value: str) -> str | None:
    if WINDOWS_ABSOLUTE_RE.match(value):
        return "windows"
    if value.startswith("/"):
        return "posix"
    return None
