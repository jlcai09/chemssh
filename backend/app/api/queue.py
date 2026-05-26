from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import get_queue_service
from backend.app.models.queue import (
    CancelJobRequest,
    CancelJobResponse,
    QueueJobActionRequest,
    QueueJobActionResponse,
    QueueJobDetailResponse,
    QueueResponse,
)
from backend.app.services.queue_service import QueueService


router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/list", response_model=QueueResponse)
def list_queue(
    current_user_only: bool = Query(default=False),
    service: QueueService = Depends(get_queue_service),
) -> QueueResponse:
    return service.list_jobs(current_user_only=current_user_only)


@router.get("/job/{job_id}", response_model=QueueJobDetailResponse)
def queue_job_detail(
    job_id: str,
    service: QueueService = Depends(get_queue_service),
) -> QueueJobDetailResponse:
    return service.job_detail(job_id)


@router.post("/cancel", response_model=CancelJobResponse)
def cancel_job(
    payload: CancelJobRequest,
    service: QueueService = Depends(get_queue_service),
) -> CancelJobResponse:
    return service.cancel_job(payload.job_id)


@router.post("/action", response_model=QueueJobActionResponse)
def run_job_action(
    payload: QueueJobActionRequest,
    service: QueueService = Depends(get_queue_service),
) -> QueueJobActionResponse:
    return service.run_action(payload.job_id, payload.action)
