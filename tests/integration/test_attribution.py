"""M5.1 on real worlds: scenario D with several irrelevant differing packages."""
import json
from pathlib import Path

import pytest

from faultline.attribution.ddmin import Budget
from faultline.attribution.runner import attribute, persist
from faultline.core.enums import WorldKind
from faultline.oracles.artifacts import prepare_artifact
from faultline.oracles.o_import import run_o_import
from faultline.resolvers.pinned import parse_pinned_lock, render_lock
from faultline.witnesses.signature import signature_of
from faultline.worlds.builder import WorldBuilder, WorldBuildError
from faultline.worlds.forced import LABEL
from tests.livefix import FIXTURES, lock_text

pytestmark = pytest.mark.docker
ENTRY, TOP = "acme_models.web", "acme_models"


@pytest.fixture(scope="module")
def lab(daemon, image):
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    sbx = SandboxClient(port=daemon.port, token=TOKEN, timeout=600)
    b = WorldBuilder(sbx, image)
    ref = parse_pinned_lock(lock_text("acme-models"))
    # consumer = notify-svc/D (werkzeug 3 breaks flask 2.2.2) + a pydantic 2 stack that is irrelevant to that failure
    cons = [p for p in parse_pinned_lock(lock_text("notify-svc/D")) if p.name != "pydantic"]
    cons += [p for p in parse_pinned_lock(lock_text("billing-svc/H")) if p.name in ("pydantic", "pydantic-core", "annotated-types")]
    cons.sort(key=lambda p: p.name)
    cw = b.materialize(render_lock(cons), WorldKind.PROJECTED)
    assert b.build(cw, render_lock(cons)).status in ("BUILT", "REUSED")
    art = prepare_artifact(FIXTURES / "acme-models", daemon.store)
    r = run_o_import(sbx, image, world_hash=cw.world_hash, artifact_hash=art, top_level=TOP, modules=[ENTRY], pythonpath=("/artifact/src",))
    e = r.entries[0]
    assert not e.passed and e.exc_type == "ImportError"
    rv, cv = {p.name: p.version for p in ref}, {p.name: p.version for p in cons}
    delta = sorted(n for n in set(rv) | set(cv) if rv.get(n) != cv.get(n))
    return sbx, image, b, art, signature_of(e, ENTRY), ref, cons, delta


def _witness_row(conn) -> str:
    from faultline.ingestion.service import create_project
    ap = create_project(conn, "x")
    conn.execute("INSERT INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES ('ep_a','i','a','l','t','{}',0)")
    conn.execute("INSERT INTO analysis(id, analysis_project_id, status, mode, options_json) VALUES ('an_a', ?, 'DONE', 'LIVE', '{}')", (ap,))
    conn.execute("INSERT INTO repository(id, analysis_project_id, owner, name) VALUES ('repo_a', ?, 'o', 'r')", (ap,))
    conn.execute("INSERT INTO snapshot(id, repository_id, sha, committed_at, store_path, ingest_status) VALUES ('snp_a','repo_a',?, 'x', 'k', 'OK')", ("a" * 40,))
    conn.execute("INSERT INTO project(id, snapshot_id, rel_path, ecosystem) VALUES ('prj_a','snp_a','.','pypi')")
    conn.execute("INSERT INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES ('w_a','pypi','{}','ep_a','reference')")
    conn.execute("INSERT INTO cell(id, analysis_id, artifact_project_id, ref_world_hash, test_world_hash, state) VALUES ('cell_a','an_a','prj_a','w_a','w_a','ANALYZED')")
    conn.execute("INSERT INTO witness(id, analysis_id, cell_id, class, divergence, oracle, oracle_version, entry_point, witness_key, signature_json, ref_pass, test_fail, body_json) "
                 "VALUES ('wit_a','an_a','cell_a','BREAK','IMPORT_ERROR','o_import','1','e','wk','{}',3,3,'{}')")
    return "wit_a"


def test_tc_5_1_2_attribution_finds_the_one_cause_among_irrelevant_differences(lab, conn):
    sbx, image, b, art, sig, ref, cons, delta = lab
    assert delta == ["annotated-types", "itsdangerous", "pydantic", "pydantic-core", "werkzeug"]
    a = attribute(sbx, image, b, artifact_hash=art, entry=ENTRY, top_level=TOP, pythonpath="/artifact/src", signature=sig, ref=ref, consumer=cons, delta=delta)
    assert a.minimal == ("werkzeug",) and a.sidedness == "two_sided" and a.status == "COMPLETE"        # equals scenario D's minimal_set
    assert a.sufficiency is True and a.necessity is True and a.minimal_claim
    searched = {tuple(x["subset"]): x for x in a.attempts if x["direction"] == "search"}
    assert searched[("itsdangerous",)]["outcome"] == "PASS" and searched[("werkzeug",)]["outcome"] == "FAIL"
    assert searched[("pydantic",)]["outcome"] == "UNRESOLVED" and any(w in searched[("pydantic",)]["note"] for w in ("failed differently", "absent"))   # never counted as a cause
    assert [x["direction"] for x in a.attempts][-2:] == ["sufficiency", "necessity"] and a.attempts[-1]["outcome"] == "PASS"
    att = persist(conn, _witness_row(conn), a)
    row = conn.execute("SELECT * FROM attribution WHERE id=?", (att,)).fetchone()
    assert row["status"] == "COMPLETE" and json.loads(row["minimal_set_json"]) == ["werkzeug"] and row["sidedness"] == "two_sided"
    assert json.loads(row["notes_json"])["label"] == LABEL
    assert conn.execute("SELECT COUNT(*) FROM attribution_attempt WHERE attribution_id=?", (att,)).fetchone()[0] == len(a.attempts)


class NoNecessityBuilder(WorldBuilder):
    """The consumer-with-the-cause-reverted world cannot be built (as if a wheel were missing)."""

    def materialize(self, lock_text, kind=WorldKind.REFERENCE, scopes=None):
        if "pydantic==2.7.4" in lock_text and "werkzeug==2.2.3" in lock_text:
            raise WorldBuildError("no matching wheel", details={"reason": "no_wheel"})
        return super().materialize(lock_text, kind, scopes)


def test_tc_5_1_3_one_sided_is_partial_and_names_the_missing_direction(lab):
    sbx, image, b, art, sig, ref, cons, delta = lab
    nb = NoNecessityBuilder(sbx, image)
    a = attribute(sbx, image, nb, artifact_hash=art, entry=ENTRY, top_level=TOP, pythonpath="/artifact/src", signature=sig, ref=ref, consumer=cons, delta=delta)
    assert a.status == "PARTIAL" and a.sidedness == "one_sided" and a.minimal == ("werkzeug",)
    assert a.necessity is None and a.sufficiency is True
    assert any("missing direction: necessity" in n for n in a.notes)
    assert a.minimal_claim is None                                                      # the UI must not say "minimal"


def test_tc_5_1_5_a_tiny_budget_is_budget_limited_not_complete(lab):
    sbx, image, b, art, sig, ref, cons, delta = lab
    a = attribute(sbx, image, b, artifact_hash=art, entry=ENTRY, top_level=TOP, pythonpath="/artifact/src", signature=sig, ref=ref, consumer=cons,
                  delta=delta, budget=Budget(max_tests=5))
    assert a.status == "BUDGET_LIMITED" and a.minimal_claim is None
    assert a.minimal == ("werkzeug",) or a.minimal is None                              # the best subset so far, if any
    assert any("budget" in n for n in a.notes)
    none = attribute(sbx, image, b, artifact_hash=art, entry=ENTRY, top_level=TOP, pythonpath="/artifact/src", signature=sig, ref=ref, consumer=cons,
                     delta=delta, budget=Budget(max_tests=1))
    assert none.status == "BUDGET_LIMITED" and none.minimal is None and Path(__file__).exists()
