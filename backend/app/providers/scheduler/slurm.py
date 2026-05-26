from __future__ import annotations

import getpass
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.app.core.errors import AppError
from backend.app.core.security import validate_job_id
from backend.app.models.job import SubmitCommand, SubmitJobResponse
from backend.app.models.queue import (
    CancelJobResponse,
    QueueJobActionResponse,
    QueueItem,
    QueueJobDetailResponse,
    QueueResponse,
)
from backend.app.providers.scheduler.base import SchedulerProvider


class SlurmProvider(SchedulerProvider):
    scheduler_name = "slurm"

    def _missing(self, command: str) -> bool:
        return shutil.which(command) is None

    def list_jobs(self, current_user_only: bool = False) -> QueueResponse:
        if self._missing("squeue"):
            return QueueResponse(
                scheduler=self.scheduler_name,
                available=False,
                message="squeue command was not found on this host",
                items=[],
            )

        json_response = self._list_jobs_json(current_user_only)
        if json_response is not None:
            return json_response
        return self._list_jobs_text(current_user_only)

    def _list_jobs_json(self, current_user_only: bool) -> QueueResponse | None:
        command = _squeue_command(current_user_only, "--json")
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or not result.stdout.strip():
            return None

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

        jobs = payload.get("jobs", [])
        items = [self._queue_item_from_json(job) for job in jobs if isinstance(job, dict)]
        if items and all(not item.workdir for item in items):
            return None
        return QueueResponse(scheduler=self.scheduler_name, items=items)

    def _queue_item_from_json(self, job: dict[str, Any]) -> QueueItem:
        resources = job.get("resources") or {}
        state = job.get("job_state") or job.get("state") or ""
        if isinstance(state, list):
            state = ",".join(str(item) for item in state)
        partition = job.get("partition") or job.get("partition_name") or ""
        reason = job.get("state_reason") or job.get("reason") or job.get("nodes") or ""
        time_obj = job.get("time") if isinstance(job.get("time"), dict) else {}
        return QueueItem(
            job_id=str(job.get("job_id") or job.get("id") or ""),
            name=str(job.get("name") or job.get("job_name") or ""),
            user=str(job.get("user_name") or job.get("user") or ""),
            state=str(state),
            partition=str(partition),
            nodes=_int_or_none(job.get("nodes") or resources.get("nodes")),
            cpus=_int_or_none(job.get("cpus") or resources.get("cpus")),
            time_used=str(job.get("time_used") or time_obj.get("elapsed") or ""),
            time_limit=str(job.get("time_limit") or time_obj.get("limit") or ""),
            reason=str(reason),
            workdir=(
                job.get("working_directory")
                or job.get("work_dir")
                or job.get("workdir")
                or job.get("current_working_directory")
            ),
        )

    def _list_jobs_text(self, current_user_only: bool) -> QueueResponse:
        fmt = "%i|%j|%u|%T|%M|%l|%D|%C|%R|%P|%Z"
        command = _squeue_command(current_user_only, "-h", "-o", fmt)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        except subprocess.TimeoutExpired as exc:
            raise AppError("SQUEUE_TIMEOUT", "squeue timed out", 504) from exc

        if result.returncode != 0:
            return QueueResponse(
                scheduler=self.scheduler_name,
                available=False,
                message=result.stderr.strip() or "squeue failed",
                items=[],
            )

        items: list[QueueItem] = []
        for line in result.stdout.splitlines():
            parts = line.split("|")
            if len(parts) < 10:
                continue
            job_id, name, user, state, used, limit, nodes, cpus, reason, partition = parts[:10]
            workdir = parts[10] if len(parts) > 10 else None
            items.append(
                QueueItem(
                    job_id=job_id.strip(),
                    name=name.strip(),
                    user=user.strip(),
                    state=state.strip(),
                    partition=partition.strip(),
                    nodes=_int_or_none(nodes),
                    cpus=_int_or_none(cpus),
                    time_used=used.strip(),
                    time_limit=limit.strip(),
                    reason=reason.strip(),
                    workdir=workdir.strip() if workdir else None,
                )
            )
        return QueueResponse(scheduler=self.scheduler_name, items=items)

    def job_detail(self, job_id: str) -> QueueJobDetailResponse:
        validate_job_id(job_id)
        if self._missing("scontrol"):
            raise AppError("SCONTROL_NOT_FOUND", "scontrol command was not found on this host", 503)

        result = subprocess.run(
            ["scontrol", "show", "job", job_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            raise AppError("JOB_DETAIL_FAILED", result.stderr.strip() or "scontrol failed", 502)
        return QueueJobDetailResponse(job_id=job_id, detail=_parse_key_value_output(result.stdout))

    def cancel_job(self, job_id: str) -> CancelJobResponse:
        validate_job_id(job_id)
        if self._missing("scancel"):
            raise AppError("SCANCEL_NOT_FOUND", "scancel command was not found on this host", 503)

        result = subprocess.run(
            ["scancel", job_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        message = result.stderr.strip() or result.stdout.strip() or f"Cancelled job {job_id}"
        if result.returncode != 0:
            raise AppError("SCANCEL_FAILED", message, 502)
        return CancelJobResponse(
            success=True,
            scheduler=self.scheduler_name,
            job_id=job_id,
            message=message,
        )

    def hold_job(self, job_id: str) -> QueueJobActionResponse:
        return self._run_scontrol_action(job_id, "hold")

    def release_job(self, job_id: str) -> QueueJobActionResponse:
        return self._run_scontrol_action(job_id, "release")

    def _run_scontrol_action(self, job_id: str, action: str) -> QueueJobActionResponse:
        validate_job_id(job_id)
        if self._missing("scontrol"):
            raise AppError("SCONTROL_NOT_FOUND", "scontrol command was not found on this host", 503)

        result = subprocess.run(
            ["scontrol", action, job_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        message = result.stderr.strip() or result.stdout.strip() or f"{action.title()} requested for job {job_id}"
        if result.returncode != 0:
            raise AppError(f"SCONTROL_{action.upper()}_FAILED", message, 502)
        return QueueJobActionResponse(
            success=True,
            scheduler=self.scheduler_name,
            job_id=job_id,
            action=action,  # type: ignore[arg-type]
            command=f"scontrol {action}",
            message=message,
        )

    def submit_job(self, workdir: Path, script: str, command: SubmitCommand = "sbatch") -> SubmitJobResponse:
        if self._missing(command):
            raise AppError(
                f"{command.upper()}_NOT_FOUND",
                f"{command} command was not found on this host",
                503,
            )

        result = subprocess.run(
            [command, script],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        message = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            raise AppError(f"{command.upper()}_FAILED", message or f"{command} failed", 502)
        match = _submitted_job_id(command, message)
        return SubmitJobResponse(
            success=True,
            scheduler=command,
            job_id=match.group(1) if match else None,
            message=message,
        )


class LocalSchedulerProvider(SchedulerProvider):
    scheduler_name = "local"

    def list_jobs(self, current_user_only: bool = False) -> QueueResponse:
        return QueueResponse(
            scheduler=self.scheduler_name,
            available=False,
            message="Local process scheduler is reserved for a later milestone",
            items=[],
        )

    def job_detail(self, job_id: str) -> QueueJobDetailResponse:
        validate_job_id(job_id)
        raise AppError("LOCAL_UNSUPPORTED", "Local job details are not implemented yet", 501)

    def cancel_job(self, job_id: str) -> CancelJobResponse:
        validate_job_id(job_id)
        raise AppError("LOCAL_UNSUPPORTED", "Local job cancel is not implemented yet", 501)

    def hold_job(self, job_id: str) -> QueueJobActionResponse:
        validate_job_id(job_id)
        raise AppError("LOCAL_UNSUPPORTED", "Local job hold is not implemented yet", 501)

    def release_job(self, job_id: str) -> QueueJobActionResponse:
        validate_job_id(job_id)
        raise AppError("LOCAL_UNSUPPORTED", "Local job release is not implemented yet", 501)

    def submit_job(self, workdir: Path, script: str, command: SubmitCommand = "sbatch") -> SubmitJobResponse:
        raise AppError("LOCAL_UNSUPPORTED", "Local job submit is not implemented yet", 501)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _squeue_command(current_user_only: bool, *args: str) -> list[str]:
    command = ["squeue"]
    if current_user_only:
        command.extend(["-u", getpass.getuser()])
    command.extend(args)
    return command


def _parse_key_value_output(text: str) -> dict[str, str]:
    detail: dict[str, str] = {}
    for token in text.replace("\n", " ").split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        detail[key] = value
    return detail


def _submitted_job_id(command: SubmitCommand, message: str) -> re.Match[str] | None:
    if command == "sbatch":
        return re.search(r"Submitted batch job\s+(\S+)", message)
    return re.search(r"\b(\d+(?:\.[A-Za-z0-9_.-]+)?)\b", message)
