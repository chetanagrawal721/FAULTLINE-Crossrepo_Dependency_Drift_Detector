from fastapi import APIRouter, Depends

from ...analysis.read import analysis_view, latest_analysis_id
from ...analysis.whypath import inventory_graph, why_path
from ...core.errors import InvalidTransitionError, NotFoundError
from ...core.ids import new_id
from ...core.models import Job
from ...core.views import AnalysisView, InventoryGraph, WhyPath
from ...ingestion import service
from ...storage import jobs
from ..deps import fresh_conn, get_conn, require_token

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/analyses/{analysis_id}", response_model=AnalysisView)
def get_analysis(analysis_id: str, conn=Depends(fresh_conn)) -> AnalysisView:
    return analysis_view(conn, analysis_id)


@router.get("/projects/{project_id}/analysis", response_model=AnalysisView)
def latest_for_project(project_id: str, conn=Depends(fresh_conn)) -> AnalysisView:
    """The most recent live analysis of a project, straight from the database."""
    service.get_project(conn, project_id)
    aid = latest_analysis_id(conn, project_id)
    if aid is None:
        raise NotFoundError("this project has not been analysed yet")
    return analysis_view(conn, aid)


@router.get("/findings/{finding_id}/why-path", response_model=WhyPath)
def finding_why_path(finding_id: str, conn=Depends(fresh_conn)) -> WhyPath:
    return why_path(conn, finding_id)


@router.get("/projects/{project_id}/inventory", response_model=InventoryGraph)
def project_inventory(project_id: str, conn=Depends(get_conn)) -> InventoryGraph:
    service.get_project(conn, project_id)
    return inventory_graph(conn, project_id)


@router.post("/witnesses/{witness_id}/rerun", response_model=Job, status_code=202, dependencies=[Depends(require_token)])
def rerun(witness_id: str, conn=Depends(get_conn)) -> Job:
    """Run the witness's oracle again (3 fresh runs per world). A live action: refused in REPLAY mode."""
    w = conn.execute("SELECT oracle FROM witness WHERE id=?", (witness_id,)).fetchone()
    if w is None:
        raise NotFoundError(f"witness {witness_id} not found")
    if w["oracle"] != "o_import":
        raise InvalidTransitionError(f"live re-run is available for import witnesses; this witness comes from {w['oracle']}. Run the analysis again to check it again.")
    job, _ = jobs.create_job(conn, "rerun_witness", {"witness_id": witness_id}, f"rerun:{witness_id}:{new_id('r')}")
    return job


@router.post("/findings/{finding_id}/remediate", response_model=Job, status_code=202, dependencies=[Depends(require_token)])
def remediate_finding(finding_id: str, conn=Depends(get_conn)) -> Job:
    """Propose and verify a constraint for the attributed cause. The result is a diff; nothing is pushed anywhere."""
    if conn.execute("SELECT 1 FROM finding WHERE id=?", (finding_id,)).fetchone() is None:
        raise NotFoundError(f"finding {finding_id} not found")
    job, _ = jobs.create_job(conn, "remediate_finding", {"finding_id": finding_id}, f"remediate:{finding_id}:{new_id('r')}")
    return job
