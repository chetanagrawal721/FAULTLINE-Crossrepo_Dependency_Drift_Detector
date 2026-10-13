from fastapi import APIRouter, Depends, Query

from ...core.errors import ErrorCode, FaultlineError
from ...core.models import Job, JobCreate
from ...storage import jobs
from ...workers.handlers import HANDLERS
from ..deps import get_conn, require_token

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=Job, status_code=202, dependencies=[Depends(require_token)])
def create_job(body: JobCreate, conn=Depends(get_conn)) -> Job:
    """Enqueue a job and return immediately. Poll GET /api/jobs/{id} for progress."""
    if body.kind not in HANDLERS:
        raise FaultlineError(f"unknown job kind {body.kind!r}", code=ErrorCode.UNKNOWN_JOB_KIND,
                             details={"known": sorted(HANDLERS)})
    job, _created = jobs.create_job(conn, body.kind, body.payload, body.idempotency_key)
    return job


@router.get("", response_model=list[Job])
def list_jobs(limit: int = Query(50, ge=1, le=200), conn=Depends(get_conn)) -> list[Job]:
    return jobs.list_jobs(conn, limit)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, conn=Depends(get_conn)) -> Job:
    return jobs.get_job(conn, job_id)


@router.post("/{job_id}/cancel", response_model=Job, dependencies=[Depends(require_token)])
def cancel_job(job_id: str, conn=Depends(get_conn)) -> Job:
    return jobs.request_cancel(conn, job_id)
