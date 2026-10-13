"""M4.3: cells deduplicate by projection, NO_DRIFT queues nothing, and failed consumers stay in the discovered count."""
import json

import pytest

from faultline.relationships.engine import create_analysis, discover
from faultline.storage.store import Store
from faultline.verdicts.stats import funnel
from faultline.worlds.cells import persist_cell, plan_cells
from tests.livefix import (
    fixture_repo,
    lock_text,
    new_analysis_project,
    seed_projects,
    seed_repository,
    seed_world,
)

ACME = "faultline-demo"


@pytest.fixture
def lab(conn, tmp_path):
    store = Store(tmp_path / "store")
    apid = new_analysis_project(conn)
    conn.execute("INSERT OR IGNORE INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES ('ep_x','i','a','l','t','{}',0)")
    conn.execute("INSERT OR IGNORE INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES ('w_projected','pypi','{}','ep_x','projected')")

    def add(name, subdir, lock=None, failure=None):
        files = fixture_repo(subdir)
        _rid, sid = seed_repository(conn, store, apid, ACME, name, files)
        pid = seed_projects(conn, store, sid)[0]
        seed_world(conn, pid, lock_text(subdir) if lock is None and not failure else lock, failure=failure)
        return pid

    return conn, store, apid, add


def build(lab_):
    conn, store, apid, _add = lab_
    aid = create_analysis(conn, apid)
    rels = discover(conn, store, aid, apid)
    return aid, rels, plan_cells(conn, rels)


def test_tc_4_3_1_identical_projections_share_one_cell_with_two_links(lab):
    conn, store, apid, add = lab
    add("acme-models", "acme-models")
    a = add("orders-svc", "notify-svc/D")
    b = add("notify-svc", "notify-svc/D")
    aid, rels, planned = build(lab)
    assert len(planned.cells) == 1 and {c for c, _ in planned.cells[0].consumers} == {a, b}
    cid = persist_cell(conn, aid, planned.cells[0], "w_projected")
    assert conn.execute("SELECT COUNT(*) FROM cell WHERE analysis_id=?", (aid,)).fetchone()[0] == 1
    assert {r["consumer_project_id"] for r in conn.execute("SELECT consumer_project_id FROM cell_consumer WHERE cell_id=?", (cid,))} == {a, b}
    assert {r["name"] for r in conn.execute("SELECT name FROM delta_entry WHERE cell_id=?", (cid,))} == {"itsdangerous", "werkzeug"}


def test_tc_4_3_2_a_consumer_matching_the_reference_is_no_drift_and_queues_no_oracle(lab):
    conn, store, apid, add = lab
    add("acme-models", "acme-models")
    add("orders-svc", "orders-svc/A")
    aid, rels, planned = build(lab)
    [plan] = planned.cells
    assert plan.projection.no_drift
    cid = persist_cell(conn, aid, plan, None)
    row = conn.execute("SELECT * FROM cell WHERE id=?", (cid,)).fetchone()
    assert row["state"] == "NO_DRIFT" and row["test_world_hash"] == row["ref_world_hash"]
    assert conn.execute("SELECT COUNT(*) FROM oracle_job").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM delta_entry WHERE cell_id=?", (cid,)).fetchone()[0] == 0


def test_tc_4_3_3_a_failed_consumer_is_counted_discovered_but_not_analysed(lab):
    conn, store, apid, add = lab
    add("acme-models", "acme-models")
    add("orders-svc", "orders-svc/A")
    add("notify-svc", "notify-svc/D")
    broken = add("billing-svc", "billing-svc/H", failure="needs_build")
    aid, rels, planned = build(lab)
    for p in planned.cells:
        persist_cell(conn, aid, p, "w_projected")
    conn.execute("UPDATE analysis SET stats_json=? WHERE id=?", (json.dumps({"failed_consumers": planned.failed}), aid))
    f = funnel(conn, aid)
    assert f["consumers_discovered"] == 3 and f["consumers_analysed"] == 2
    assert [x["consumer"] for x in f["consumers_failed"]] == [broken] and f["consumers_failed"][0]["reason"] == "needs_build"
    assert f["cells"] == 2 and f["cells_by_state"] == {"NO_DRIFT": 1, "PENDING": 1}
    assert "score" not in json.dumps(f).lower()


def test_unavailable_reference_fails_every_consumer_without_a_cell(lab):
    conn, store, apid, add = lab
    add("acme-models", "acme-models", failure="no_manifest")
    add("notify-svc", "notify-svc/D")
    aid, rels, planned = build(lab)
    assert planned.cells == [] and planned.failed[0]["side"] == "reference" and planned.failed[0]["reason"] == "no_manifest"
