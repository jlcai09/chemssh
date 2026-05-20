from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.models.job import SubmitCommand, SubmitJobResponse
from backend.app.models.queue import (
    CancelJobResponse,
    QueueJobActionResponse,
    QueueJobDetailResponse,
    QueueResponse,
)


class SchedulerProvider(ABC):
    scheduler_name: str

    @abstractmethod
    def list_jobs(self) -> QueueResponse:
        raise NotImplementedError

    @abstractmethod
    def job_detail(self, job_id: str) -> QueueJobDetailResponse:
        raise NotImplementedError

    @abstractmethod
    def cancel_job(self, job_id: str) -> CancelJobResponse:
        raise NotImplementedError

    @abstractmethod
    def hold_job(self, job_id: str) -> QueueJobActionResponse:
        raise NotImplementedError

    @abstractmethod
    def release_job(self, job_id: str) -> QueueJobActionResponse:
        raise NotImplementedError

    @abstractmethod
    def submit_job(self, workdir: Path, script: str, command: SubmitCommand = "sbatch") -> SubmitJobResponse:
        raise NotImplementedError
