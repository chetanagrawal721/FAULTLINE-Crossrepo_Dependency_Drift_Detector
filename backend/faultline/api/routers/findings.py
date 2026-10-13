import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ...core.config import Settings
from ...core.errors import NotFoundError
from ...core.models import Job
from ...core.scenario import load_scenario
from ...core.views import FindingDetail, FindingSummary, ScenarioConsumer, ScenarioInfo
from ...storage import findings as finding_store
from ...storage import jobs
from ...storage.store import Store
from ...witnesses.bundle import write_bundle
from ..deps import fresh_conn, get_conn, get_settings, require_token

router = APIRouter(prefix="/api", tags=["findings"])


def _scenario_dir() -> Path:
    from ...core.config import repo_root
    return repo_root() / "fixtures" / "scenarios"


@router.get("/scenarios", response_model=list[ScenarioInfo])
def list_scenarios() -> list[ScenarioInfo]:
    out = []
    for f in sorted(_scenario_dir().glob("*.yaml")):
        sc = load_scenario(f)
        cells = {c.consumer: c for c in sc.expect.cells}
        sc.consumers = [c for c in sc.consumers if c.repo in cells]
        out.append(ScenarioInfo(
            id=sc.id, title=sc.title, kind=sc.kind, artifact=sc.artifact.repo,
            consumers=[ScenarioConsumer(repo=c.repo, expected_state=cells[c.repo].state,
                                        expected_verdict=cells[c.repo].verdict.value if cells[c.repo].verdict else None,
                                        expects_witness=cells[c.repo].witness) for c in sc.consumers]))
    return out


@router.post("/scenarios/{scenario_id}/run", response_model=Job, status_code=202, dependencies=[Depends(require_token)])
def run_scenario(scenario_id: str, conn=Depends(get_conn)) -> Job:
    """Queue a fixture scenario. The worker executes it; poll GET /api/jobs/{id}."""
    if not (_scenario_dir() / f"{scenario_id}.yaml").exists():
        raise NotFoundError(f"scenario {scenario_id} not found")
    job, _ = jobs.create_job(conn, "fixture_scenario", {"scenario_id": scenario_id})
    return job


@router.get("/findings", response_model=list[FindingSummary])
def list_findings(verdict: str | None = None, mode: str | None = None, conn=Depends(fresh_conn)) -> list[FindingSummary]:
    """All findings, newest first. Optional filters: ?verdict=BREAK_WITNESSED&mode=LIVE."""
    return [f for f in finding_store.list_findings(conn) if (not verdict or f.verdict == verdict) and (not mode or f.mode == mode)]


@router.get("/findings/{finding_id}", response_model=FindingDetail)
def get_finding(finding_id: str, conn=Depends(fresh_conn)) -> FindingDetail:
    return finding_store.get_finding(conn, finding_id, bundle_url=None)


@router.get("/witnesses/{witness_id}/bundle/manifest")
def witness_bundle_manifest(witness_id: str, conn=Depends(get_conn), settings: Settings = Depends(get_settings)) -> dict:
    """What a witness's evidence bundle contains and whether it verifies: the manifest, every file with its SHA-256, and the verifier's verdict."""
    from ...witnesses.bundle import verify_bundle
    row = conn.execute("SELECT w.id, a.mode FROM witness w JOIN analysis a ON a.id = w.analysis_id WHERE w.id=?", (witness_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"witness {witness_id} not found")
    if settings.mode.value == "REPLAY":
        path = Path(settings.store_path) / "bundles" / f"{witness_id}.zip"
        if not path.is_file():
            raise NotFoundError(f"no recorded bundle for witness {witness_id}")
        check = verify_bundle(path)
    else:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bundle.zip"
            write_bundle(conn, witness_id, path, Store(settings.store_path), mode=row["mode"])
            check = verify_bundle(path)
    m = check.manifest or {}
    return {"witness_id": witness_id, "verified": check.ok, "errors": check.errors, "schema_version": m.get("schema_version"), "bundle_id": m.get("bundle_id"),
            "created_at": m.get("created_at"), "mode": m.get("mode"), "oracle": m.get("oracle"), "worlds": m.get("worlds"), "artifact": m.get("artifact"),
            "run_summary": m.get("run_summary"), "claim": m.get("claim"), "files": m.get("files", [])}


@router.get("/witnesses/{witness_id}/bundle")
def witness_bundle(witness_id: str, conn=Depends(get_conn), settings: Settings = Depends(get_settings)) -> Response:
    """The evidence bundle for a witness, generated from the stored records and verified before it is served."""
    from ...witnesses.bundle import verify_bundle
    row = conn.execute("SELECT w.id, a.mode FROM witness w JOIN analysis a ON a.id = w.analysis_id WHERE w.id=?",
                       (witness_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"witness {witness_id} not found")
    if settings.mode.value == "REPLAY":                          # recorded evidence: serve the pre-built, pre-verified bundle only
        pre = Path(settings.store_path) / "bundles" / f"{witness_id}.zip"
        if not pre.is_file():
            raise NotFoundError(f"no recorded bundle for witness {witness_id}")
        return Response(content=pre.read_bytes(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="faultline-evidence-{witness_id}.zip"'})
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "bundle.zip"
        write_bundle(conn, witness_id, path, Store(settings.store_path), mode=row["mode"])
        check = verify_bundle(path)
        if not check.ok:
            raise RuntimeError(f"generated bundle failed verification: {check.errors}")
        data = path.read_bytes()
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="faultline-evidence-{witness_id}.zip"'})
