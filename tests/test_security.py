from pathlib import Path

import pytest

from backend.app.core.errors import AppError
from backend.app.core.security import WorkspaceSecurity, validate_job_id, validate_script_name


def test_workspace_security_allows_root_child(tmp_path: Path) -> None:
    security = WorkspaceSecurity(tmp_path)

    assert security.resolve_path("project") == (tmp_path / "project").resolve(strict=False)


def test_workspace_security_blocks_traversal(tmp_path: Path) -> None:
    security = WorkspaceSecurity(tmp_path)

    with pytest.raises(AppError) as exc:
        security.resolve_path("../outside")

    assert exc.value.code == "FORBIDDEN_PATH"


def test_workspace_security_rejects_windows_path_for_posix_workspace() -> None:
    security = WorkspaceSecurity("/data/user/workspace")  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc:
        security.resolve_path("D:\\Git\\chemssh")

    assert exc.value.code == "INVALID_PATH_PLATFORM"


def test_validate_script_name_rejects_shell_fragments() -> None:
    with pytest.raises(AppError):
        validate_script_name("run.sh;rm")

    with pytest.raises(AppError):
        validate_script_name("../run.sh")

    assert validate_script_name("run.sh") == "run.sh"


def test_validate_job_id() -> None:
    assert validate_job_id("123456.batch") == "123456.batch"

    with pytest.raises(AppError):
        validate_job_id("123;rm")
