from fastapi import APIRouter, Depends

from ...analysis.read import analysis_view, latest_analysis_id
from ...core.errors import NotFoundError
from ...core.views import AnalysisView
from ...ingestion import service
from ..deps import get_conn

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/analyses/{analysis_id}", response_model=AnalysisView)
def get_analysis(analysis_id: str, conn=Depends(get_conn)) -> AnalysisView:
    return analysis_view(conn, analysis_id)


@router.get("/projects/{project_id}/analysis", response_model=AnalysisView)
def latest_for_project(project_id: str, conn=Depends(get_conn)) -> AnalysisView:
    """The most recent live analysis of a project, straight from the database."""
    service.get_project(conn, project_id)
    aid = latest_analysis_id(conn, project_id)
    if aid is None:
        raise NotFoundError("this project has not been analysed yet")
    return analysis_view(conn, aid)
