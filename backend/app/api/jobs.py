from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_job_service
from backend.app.models.job import SubmitJobRequest, SubmitJobResponse
from backend.app.services.job_service import JobService


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/submit", response_model=SubmitJobResponse)
def submit_job(
    payload: SubmitJobRequest,
    service: JobService = Depends(get_job_service),
) -> SubmitJobResponse:
    return service.submit(payload)
