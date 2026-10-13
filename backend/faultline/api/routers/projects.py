from fastapi import APIRouter, Depends, Query, Request

from ...core.errors import FaultlineError, InvalidTransitionError, NotFoundError
from ...core.ids import new_id
from ...core.models import Job
from ...core.views import FileView, ProjectCreate, ProjectView, RepositoryCreate, RepositoryView
from ...ingestion import service
from ...ingestion.github import GitHubClient
from ...ingestion.views import file_views, project_view, repository_view
from ...storage import jobs
from ..deps import get_conn, require_token

router = APIRouter(prefix="/api", tags=["projects"])


def get_github(request: Request) -> GitHubClient:
    return getattr(request.app.state, "github", None) or GitHubClient()


def _queue_ingest(conn, repository_id: str, sha: str, nonce: str = "") -> Job:
    # one in-flight job per (repository, pinned sha): resubmitting is idempotent until a retry asks for a new one
    job, _ = jobs.create_job(conn, "ingest_repository", {"repository_id": repository_id, "sha": sha},
                             f"ingest:{repository_id}:{sha}:{nonce}")
    return job


@router.post("/projects", response_model=ProjectView, status_code=201, dependencies=[Depends(require_token)])
def create_project(body: ProjectCreate, conn=Depends(get_conn)) -> ProjectView:
    name = body.name.strip()
    if not name or len(name) > 80:
        raise FaultlineError("project name must be 1 to 80 characters")
    return project_view(conn, service.get_project(conn, service.create_project(conn, name)))


@router.get("/projects", response_model=list[ProjectView])
def list_projects(mode: str | None = Query(None, pattern="^(LIVE|FIXTURE|REPLAY)$"), conn=Depends(get_conn)) -> list[ProjectView]:
    """Newest first. The fixture pipeline keeps its own FIXTURE projects; pass mode=LIVE for user-submitted repositories."""
    sql, args = "SELECT * FROM analysis_project", []
    if mode:
        sql, args = sql + " WHERE mode=?", [mode]
    return [project_view(conn, r) for r in conn.execute(sql + " ORDER BY created_at DESC, id DESC", args)]


@router.get("/projects/{project_id}", response_model=ProjectView)
def get_project(project_id: str, conn=Depends(get_conn)) -> ProjectView:
    return project_view(conn, service.get_project(conn, project_id))


@router.post("/projects/{project_id}/repositories", response_model=RepositoryView, status_code=202,
             dependencies=[Depends(require_token)])
def add_repository(project_id: str, body: RepositoryCreate, conn=Depends(get_conn),
                   github: GitHubClient = Depends(get_github)) -> RepositoryView:
    """Validate the URL, resolve the ref to a commit SHA now, then ingest that SHA in a background job."""
    rid, resolved, _changed = service.add_repository(conn, github, project_id, body.url, body.ref)
    row = service.get_repository(conn, rid)
    job = None
    if row["status"] == "FAILED":                       # submitting a failed repository again is a retry of the same SHA
        conn.execute("UPDATE repository SET status='PENDING', error_json=NULL WHERE id=?", (rid,))
        job = _queue_ingest(conn, rid, resolved.sha, new_id("r"))
    elif row["status"] != "INGESTED":
        job = _queue_ingest(conn, rid, resolved.sha)
    return repository_view(conn, service.get_repository(conn, rid), job.job_id if job else None)


@router.get("/repositories/{repository_id}", response_model=RepositoryView)
def get_repository(repository_id: str, conn=Depends(get_conn)) -> RepositoryView:
    return repository_view(conn, service.get_repository(conn, repository_id))


@router.get("/repositories/{repository_id}/files", response_model=list[FileView])
def list_files(repository_id: str, role: str | None = Query(None, max_length=40), limit: int = Query(500, ge=1, le=5000),
               offset: int = Query(0, ge=0), conn=Depends(get_conn)) -> list[FileView]:
    repo = service.get_repository(conn, repository_id)
    return file_views(conn, repository_id, repo["pinned_sha"], role, limit, offset)


@router.post("/repositories/{repository_id}/retry", response_model=RepositoryView, status_code=202,
             dependencies=[Depends(require_token)])
def retry_ingest(repository_id: str, conn=Depends(get_conn)) -> RepositoryView:
    """Re-run ingestion for the SAME pinned SHA. To pick up a moved ref, submit the repository again."""
    repo = service.get_repository(conn, repository_id)
    if repo["status"] != "FAILED":
        raise InvalidTransitionError(f"only a FAILED ingestion can be retried (this one is {repo['status']})")
    if not repo["pinned_sha"]:
        raise NotFoundError("repository has no pinned SHA")
    conn.execute("UPDATE repository SET status='PENDING', error_json=NULL WHERE id=?", (repository_id,))
    job = _queue_ingest(conn, repository_id, repo["pinned_sha"], new_id("r"))
    return repository_view(conn, service.get_repository(conn, repository_id), job.job_id)


@router.post("/projects/{project_id}/analyze", response_model=Job, status_code=202, dependencies=[Depends(require_token)])
def analyze_project(project_id: str, conn=Depends(get_conn)) -> Job:
    """Run the live cross-repository analysis over the repositories already ingested into this project."""
    service.get_project(conn, project_id)
    ingested = conn.execute("SELECT COUNT(*) FROM repository WHERE analysis_project_id=? AND status='INGESTED'", (project_id,)).fetchone()[0]
    if ingested < 2:
        raise InvalidTransitionError(f"a cross-repository analysis needs at least 2 ingested repositories (this project has {ingested})")
    job, _ = jobs.create_job(conn, "live_analysis", {"analysis_project_id": project_id}, f"live:{project_id}:{new_id('r')}")
    return job
