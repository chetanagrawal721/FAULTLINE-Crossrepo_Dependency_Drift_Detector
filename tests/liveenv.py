"""Real end-to-end setup for the live pipeline: local git remotes -> sandboxed fetch -> ingest -> analyse (worlds built)."""
from faultline.analysis.repository import analyze_repository
from faultline.ingestion import service
from tests.gitremote import Remote
from tests.integration.test_ingestion import make_fake_github


def nest(files: dict[str, bytes]) -> dict:
    root: dict = {}
    for path, data in files.items():
        cur = root
        parts = path.split("/")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = data
    return root


def ingest_all(conn, sbx, image, store, repos: dict[str, tuple[str, dict[str, bytes]]], apid: str | None = None) -> tuple[str, dict[str, str]]:
    """repos: remote_name -> (owner/name, files). Returns (analysis_project_id, {owner/name: repository_id})."""
    apid = apid or service.create_project(conn, "live")
    ids = {}
    for remote, (slug, files) in repos.items():
        sha = Remote(store.remote_dir(remote)).commit(nest(files))
        rid, _, _ = service.add_repository(conn, make_fake_github({"main": sha}), apid, f"https://github.com/{slug}")
        service.ingest(conn, sbx, image, store, rid, remote=remote)
        analyze_repository(conn, sbx, image, store, rid)
        ids[slug] = rid
    return apid, ids
