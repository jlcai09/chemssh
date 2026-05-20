from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


SubmitCommand = Literal["sbatch", "qsub"]


class SubmitJobRequest(BaseModel):
    workdir: str
    script: str = "run.sh"
    scheduler: str = "slurm"
    command: SubmitCommand = "sbatch"


class SubmitJobResponse(BaseModel):
    success: bool
    scheduler: str
    job_id: str | None = None
    message: str
