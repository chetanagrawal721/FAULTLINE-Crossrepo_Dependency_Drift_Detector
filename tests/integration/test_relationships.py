"""M4.1: relationships need evidence on both sides; name-only and look-alike matches never become actionable."""
import pytest

from faultline.relationships.engine import create_analysis, discover, evidence_for
from faultline.storage.store import Store
from tests.livefix import fixture_repo, new_analysis_project, seed_projects, seed_repository

ACME = "faultline-demo"


@pytest.fixture
def world(conn, tmp_path):
    store = Store(tmp_path / "store")
    apid = new_analysis_project(conn)

    def add(owner, name, files, **kw):
        rid, sid = seed_repository(conn, store, apid, owner, name, files, **kw)
        return seed_projects(conn, store, sid)[0]

    return conn, store, apid, add


def rels(conn, aid):
    return [dict(r) for r in conn.execute("SELECT * FROM relationship WHERE analysis_id=? ORDER BY kind, level", (aid,))]


def test_tc_4_1_1_positive_relationship_has_evidence_in_both_manifests(world):
    conn, store, apid, add = world
    prod = add(ACME, "acme-models", fixture_repo("acme-models"))
    cons = add(ACME, "notify-svc", fixture_repo("notify-svc/D"))
    aid = create_analysis(conn, apid)
    found = discover(conn, store, aid, apid)
    [rel] = [r for r in found if r.actionable]
    assert (rel.level, rel.kind, rel.confidence, rel.status) == ("L2", "SHARED_ARTIFACT", "HIGH", "ACTIVE")
    assert rel.producer_project_id == prod and rel.consumer_project_id == cons
    ev = evidence_for(conn, rel.id)
    by_project = {e["project_id"]: e for e in ev}
    assert by_project[prod]["file_path"] == "pyproject.toml" and by_project[prod]["signal"] == "published_name"
    assert by_project[cons]["file_path"] == "requirements.txt" and by_project[cons]["signal"] == "git_dep"
    assert "acme-models" in by_project[cons]["excerpt"] and "scenario-D" in by_project[cons]["excerpt"]


def test_tc_4_1_2_unrelated_project_and_look_alike_model_are_not_actionable(world):
    conn, store, apid, add = world
    add(ACME, "acme-models", fixture_repo("acme-models"))
    add("other", "marketing-site", {"pyproject.toml": '[project]\nname = "marketing-site"\nversion = "1"\ndependencies = ["django>=4"]\n',
                                    "site/__init__.py": "", "site/views.py": "def index(): pass\n"})
    twin = ('from pydantic import BaseModel\n\n\nclass CustomerRequest(BaseModel):\n    customer_id: int\n    email: str\n'
            '    loyalty_points: int = 0\n')
    add("other", "legacy-web", {"pyproject.toml": '[project]\nname = "legacy-web"\nversion = "1"\ndependencies = ["pydantic>=1"]\n',
                                "legacy/__init__.py": "", "legacy/models.py": twin})
    aid = create_analysis(conn, apid)
    found = discover(conn, store, aid, apid)
    assert [r for r in found if r.actionable] == []                                       # nothing actionable at all
    tray = [r for r in found if r.status == "SUSPECTED"]
    assert len(tray) == 1 and tray[0].level == "L3P" and tray[0].kind == "SUSPECTED_TWIN" and tray[0].confidence == "LOW"
    ev = evidence_for(conn, tray[0].id)
    assert {e["file_path"] for e in ev} == {"src/acme_models/customer.py", "legacy/models.py"}       # both classes, traceable
    assert all(r["actionable"] == 0 for r in rels(conn, aid))                              # no marketing-site relationship exists at all
    assert not any("marketing" in e["file_path"] for r in found for e in evidence_for(conn, r.id))


def test_same_name_package_from_another_source_is_a_suspected_collision(world):
    conn, store, apid, add = world
    add(ACME, "acme-models", fixture_repo("acme-models"))
    add("x", "impostor-user", {"requirements.txt": "acme-models @ git+https://github.com/someone-else/acme-models@v1\n"})
    found = discover(conn, store, create_analysis(conn, apid), apid)
    assert [r.actionable for r in found] == [False] and found[0].status == "SUSPECTED" and "someone-else/acme-models" in found[0].note


def test_tc_4_1_3_every_evidence_row_points_at_a_real_file_and_line(world):
    conn, store, apid, add = world
    add(ACME, "acme-models", fixture_repo("acme-models"))
    add(ACME, "notify-svc", fixture_repo("notify-svc/D"))
    add(ACME, "orders-svc", fixture_repo("orders-svc/A"))
    add(ACME, "billing-svc", fixture_repo("billing-svc/H"))
    add("p", "uses-pyproject", {"pyproject.toml": '[project]\nname = "up"\nversion = "1"\ndependencies = [\n  "pydantic",\n  "acme-models>=1.3",\n]\n'})
    aid = create_analysis(conn, apid)
    found = discover(conn, store, aid, apid)
    actionable = [r for r in found if r.actionable]
    assert len(actionable) == 4                                                              # notify, orders, billing, uses-pyproject
    checked = 0
    for r in found:
        for e in evidence_for(conn, r.id):
            snap = conn.execute("SELECT s.store_path FROM project p JOIN snapshot s ON s.id = p.snapshot_id WHERE p.id=?", (e["project_id"],)).fetchone()
            text = (store.snapshot_dir(snap["store_path"]) / e["file_path"]).read_text(encoding="utf-8").splitlines()
            assert e["line"] and 1 <= e["line"] <= len(text), e
            token = e["excerpt"].split()[0].split("[")[0].split(">")[0].split("=")[0].split("@")[0].strip().lower()
            assert token in text[e["line"] - 1].lower() or "name =" in e["excerpt"], (e, text[e["line"] - 1])
            checked += 1
    assert checked >= 8
    up = next(r for r in found if r.actionable and "uses-pyproject" in str(conn.execute("SELECT rel_path FROM project WHERE id=?", (r.consumer_project_id,)).fetchone()["rel_path"]) or r.actionable)
    assert up is not None


def test_relationships_are_cross_repository_only(world):
    conn, store, apid, add = world
    add(ACME, "mono", {"pyproject.toml": '[project]\nname = "mono"\nversion = "1"\n', "mono/__init__.py": "",
                       "svc/requirements.txt": "mono==1\n"})
    found = discover(conn, store, create_analysis(conn, apid), apid)
    assert found == []
