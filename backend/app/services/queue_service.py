from __future__ import annotations

from backend.app.models.queue import (
    CancelJobResponse,
    QueueJobAction,
    QueueJobActionResponse,
    QueueJobDetailResponse,
    QueueResponse,
)
from backend.app.providers.scheduler.base import SchedulerProvider


class QueueService:
    def __init__(self, provider: SchedulerProvider) -> None:
        self.provider = provider

    def list_jobs(self) -> QueueResponse:
        return self.provider.list_jobs()

    def job_detail(self, job_id: str) -> QueueJobDetailResponse:
        return self.provider.job_detail(job_id)

    def cancel_job(self, job_id: str) -> CancelJobResponse:
        return self.provider.cancel_job(job_id)

    def run_action(self, job_id: str, action: QueueJobAction) -> QueueJobActionResponse:
        if action == "hold":
            return self.provider.hold_job(job_id)
        if action == "release":
            return self.provider.release_job(job_id)
        cancel_response = self.provider.cancel_job(job_id)
        return QueueJobActionResponse(
            success=cancel_response.success,
            scheduler=cancel_response.scheduler,
            job_id=cancel_response.job_id,
            action="cancel",
            command="qdel" if cancel_response.scheduler.lower() == "pbs" else "scancel",
            message=cancel_response.message,
        )
