from __future__ import annotations

from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.core.security import WorkspaceSecurity, validate_script_name
from backend.app.models.job import SubmitJobRequest, SubmitJobResponse
from backend.app.providers.scheduler.base import SchedulerProvider


class JobService:
    def __init__(self, settings: Settings, provider: SchedulerProvider) -> None:
        self.settings = settings
        self.provider = provider
        self.security = WorkspaceSecurity(settings.workspace.root)

    def submit(self, payload: SubmitJobRequest) -> SubmitJobResponse:
        if payload.scheduler.lower() != self.provider.scheduler_name:
            raise AppError(
                "SCHEDULER_MISMATCH",
                f"Configured scheduler is {self.provider.scheduler_name}, got {payload.scheduler}",
                400,
            )

        script = validate_script_name(payload.script)
        workdir = self.security.resolve_path(payload.workdir)
        if not workdir.exists() or not workdir.is_dir():
            raise AppError("WORKDIR_NOT_FOUND", f"Workdir not found: {workdir}", 404)

        script_path = (workdir / script).resolve(strict=False)
        if not self.security.is_allowed(script_path):
            raise AppError("FORBIDDEN_PATH", f"Script is outside workspace root: {script}", 403)
        if not script_path.exists() or not script_path.is_file():
            raise AppError("SCRIPT_NOT_FOUND", f"Script not found: {script_path}", 404)

        return self.provider.submit_job(workdir, script, payload.command)
