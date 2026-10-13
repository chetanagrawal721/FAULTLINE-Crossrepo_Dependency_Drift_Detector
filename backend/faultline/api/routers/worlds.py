from fastapi import APIRouter, Depends

from ...core.errors import InvalidTransitionError, NotFoundError
from ...core.ids import new_id
from ...core.models import Job
from ...core.views import ProjectDetail
from ...ingestion import service
from ...storage import jobs
from ...worlds.inspector import project_details
from ..deps import get_conn, require_token

router = APIRouter(prefix="/api", tags=["worlds"])


@router.post("/repositories/{repository_id}/analyze", response_model=Job, status_code=202, dependencies=[Depends(require_token)])
def analyze(repository_id: str, conn=Depends(get_conn)) -> Job:
    """Discover projects in the pinned snapshot and resolve their dependency worlds (a background job)."""
    repo = service.get_repository(conn, repository_id)
    if repo["status"] != "INGESTED":
        raise InvalidTransitionError(f"repository is {repo['status']}; ingest it first")
    payload = {"repository_id": repository_id, "sha": repo["pinned_sha"]}
    key = f"analyze:{repository_id}:{repo['pinned_sha']}"
    job, created = jobs.create_job(conn, "analyze_repository", payload, key)
    if not created and job.status in ("DONE", "FAILED", "CANCELLED"):      # finished earlier: run again (cached steps are reused)
        job, _ = jobs.create_job(conn, "analyze_repository", payload, f"{key}:{new_id('r')}")
    return job


@router.get("/repositories/{repository_id}/projects", response_model=list[ProjectDetail])
def projects(repository_id: str, conn=Depends(get_conn)) -> list[ProjectDetail]:
    repo = service.get_repository(conn, repository_id)
    snap = conn.execute("SELECT id FROM snapshot WHERE repository_id=? AND sha=?", (repository_id, repo["pinned_sha"])).fetchone()
    if snap is None:
        raise NotFoundError("this repository has no snapshot yet")
    return project_details(conn, snap["id"])


@router.get("/projects/{project_id}/world", response_model=ProjectDetail)
def project_world(project_id: str, conn=Depends(get_conn)) -> ProjectDetail:
    p = conn.execute("SELECT snapshot_id FROM project WHERE id=?", (project_id,)).fetchone()
    if p is None:
        raise NotFoundError(f"project {project_id} not found")
    return next(d for d in project_details(conn, p["snapshot_id"]) if d.project_id == project_id)
