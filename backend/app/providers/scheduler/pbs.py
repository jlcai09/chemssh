from __future__ import annotations

import getpass
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
    QueueItem,
    QueueJobActionResponse,
    QueueJobDetailResponse,
    QueueResponse,
)
from backend.app.providers.scheduler.base import SchedulerProvider


class PbsProvider(SchedulerProvider):
    scheduler_name = "pbs"

    def _missing(self, command: str) -> bool:
        return shutil.which(command) is None

    def list_jobs(self) -> QueueResponse:
        if self._missing("qstat"):
            return QueueResponse(
                scheduler=self.scheduler_name,
                available=False,
                message="qstat command was not found on this host",
                items=[],
            )

        full_response = self._list_jobs_full()
        if full_response is not None:
            return full_response
        return self._list_jobs_summary()

    def _list_jobs_full(self) -> QueueResponse | None:
        commands = [
            ["qstat", "-f", "-u", getpass.getuser()],
            ["qstat", "-u", getpass.getuser(), "-f"],
        ]
        for command in commands:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode != 0:
                continue
            return QueueResponse(
                scheduler=self.scheduler_name,
                items=[_queue_item_from_pbs_fields(job_id, fields) for job_id, fields in _parse_qstat_full(result.stdout)],
            )

        return None

    def _list_jobs_summary(self) -> QueueResponse:
        command = ["qstat", "-u", getpass.getuser()]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        except subprocess.TimeoutExpired as exc:
            raise AppError("QSTAT_TIMEOUT", "qstat timed out", 504) from exc

        if result.returncode != 0:
            return QueueResponse(
                scheduler=self.scheduler_name,
                available=False,
                message=result.stderr.strip() or "qstat failed",
                items=[],
            )

        items: list[QueueItem] = []
        for item in (_queue_item_from_qstat_summary(line) for line in result.stdout.splitlines()):
            if item is None:
                continue
            fields = self._detail_fields(item.job_id)
            items.append(_queue_item_from_pbs_fields(item.job_id, fields) if fields else item)
        return QueueResponse(scheduler=self.scheduler_name, items=items)

    def job_detail(self, job_id: str) -> QueueJobDetailResponse:
        validate_job_id(job_id)
        if self._missing("qstat"):
            raise AppError("QSTAT_NOT_FOUND", "qstat command was not found on this host", 503)

        result = subprocess.run(
            ["qstat", "-f", job_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode != 0:
            raise AppError("JOB_DETAIL_FAILED", result.stderr.strip() or "qstat failed", 502)

        records = _parse_qstat_full(result.stdout)
        detail = records[0][1] if records else {"raw": result.stdout}
        return QueueJobDetailResponse(job_id=job_id, detail=detail)

    def _detail_fields(self, job_id: str) -> dict[str, str] | None:
        try:
            result = subprocess.run(
                ["qstat", "-f", job_id],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        records = _parse_qstat_full(result.stdout)
        return records[0][1] if records else None

    def cancel_job(self, job_id: str) -> CancelJobResponse:
        response = self._run_q_action(job_id, "cancel", "qdel")
        return CancelJobResponse(
            success=response.success,
            scheduler=response.scheduler,
            job_id=response.job_id,
            message=response.message,
        )

    def hold_job(self, job_id: str) -> QueueJobActionResponse:
        return self._run_q_action(job_id, "hold", "qhold")

    def release_job(self, job_id: str) -> QueueJobActionResponse:
        return self._run_q_action(job_id, "release", "qrls")

    def _run_q_action(self, job_id: str, action: str, command_name: str) -> QueueJobActionResponse:
        validate_job_id(job_id)
        if self._missing(command_name):
            raise AppError(f"{command_name.upper()}_NOT_FOUND", f"{command_name} command was not found on this host", 503)

        result = subprocess.run(
            [command_name, job_id],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        message = result.stderr.strip() or result.stdout.strip() or f"{command_name} requested for job {job_id}"
        if result.returncode != 0:
            raise AppError(f"{command_name.upper()}_FAILED", message, 502)
        return QueueJobActionResponse(
            success=True,
            scheduler=self.scheduler_name,
            job_id=job_id,
            action=action,  # type: ignore[arg-type]
            command=command_name,
            message=message,
        )

    def submit_job(self, workdir: Path, script: str, command: SubmitCommand = "qsub") -> SubmitJobResponse:
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
        match = _submitted_job_id(message)
        return SubmitJobResponse(
            success=True,
            scheduler=command,
            job_id=match.group(1) if match else None,
            message=message,
        )


def _parse_qstat_full(text: str) -> list[tuple[str, dict[str, str]]]:
    records: list[tuple[str, dict[str, str]]] = []
    job_id: str | None = None
    fields: dict[str, str] = {}
    current_key: str | None = None

    def save_current() -> None:
        if job_id is not None:
            records.append((job_id, dict(fields)))

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("Job Id:"):
            save_current()
            job_id = stripped.split(":", 1)[1].strip()
            fields = {}
            current_key = None
            continue
        if job_id is None:
            continue
        if "=" in stripped:
            key, value = stripped.split("=", 1)
            current_key = key.strip()
            fields[current_key] = value.strip()
        elif current_key:
            fields[current_key] = f"{fields[current_key]}{stripped}"

    save_current()
    return records


def _queue_item_from_pbs_fields(job_id: str, fields: dict[str, str]) -> QueueItem:
    owner = fields.get("Job_Owner", "")
    return QueueItem(
        job_id=job_id,
        name=fields.get("Job_Name", ""),
        user=owner.split("@", 1)[0],
        state=_pbs_state_label(fields.get("job_state", "")),
        partition=fields.get("queue", ""),
        nodes=_int_or_none(fields.get("Resource_List.nodect") or fields.get("Resource_List.nodes")),
        cpus=_int_or_none(fields.get("Resource_List.ncpus")) or _parse_select_ncpus(fields.get("Resource_List.select", "")),
        time_used=fields.get("resources_used.walltime", ""),
        time_limit=fields.get("Resource_List.walltime", ""),
        reason=fields.get("comment", "") or fields.get("Hold_Types", ""),
        workdir=_pbs_workdir(fields),
    )


def _queue_item_from_qstat_summary(line: str) -> QueueItem | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("-") or stripped.lower().startswith("job id"):
        return None

    parts = stripped.split()
    if len(parts) < 6:
        return None

    job_id, name, user, time_used, state, queue = parts[:6]
    return QueueItem(
        job_id=job_id,
        name=name,
        user=user,
        state=_pbs_state_label(state),
        partition=queue,
        time_used=time_used,
    )


def _pbs_workdir(fields: dict[str, str]) -> str | None:
    for key in ("init_work_dir", "workdir", "PBS_O_WORKDIR"):
        value = fields.get(key)
        if value:
            return value

    variable_list = fields.get("Variable_List", "")
    match = re.search(r"(?:^|,)PBS_O_WORKDIR=([^,]+)", variable_list)
    if match:
        return match.group(1)
    return None


def _pbs_state_label(state: str) -> str:
    normalized = state.strip().upper()
    labels = {
        "B": "ARRAY",
        "C": "COMPLETED",
        "E": "EXITING",
        "F": "FINISHED",
        "H": "HELD",
        "M": "MOVED",
        "Q": "PENDING",
        "R": "RUNNING",
        "S": "SUSPENDED",
        "T": "TRANSITING",
        "U": "SUSPENDED",
        "W": "WAITING",
    }
    return labels.get(normalized, normalized)


def _parse_select_ncpus(select_value: str) -> int | None:
    if not select_value:
        return None

    total = 0
    found = False
    for chunk in select_value.split("+"):
        multiplier = 1
        chunk_parts = chunk.split(":")
        if chunk_parts and chunk_parts[0].isdigit():
            multiplier = int(chunk_parts[0])
            chunk_parts = chunk_parts[1:]
        for part in chunk_parts:
            if not part.startswith("ncpus="):
                continue
            try:
                total += multiplier * int(part.split("=", 1)[1])
                found = True
            except ValueError:
                continue
    return total if found else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _submitted_job_id(message: str) -> re.Match[str] | None:
    return re.search(r"\b(\d+(?:\.[A-Za-z0-9_.-]+)?)\b", message)
