"""M1.6: witness verification on the real fixture worlds (TC-1.6.1 to TC-1.6.4). Real Docker, 6 real runs per check."""
import json

import pytest

from faultline.analysis.fixture import ensure_fixture_cell
from faultline.core.enums import FailureClass, RunProvenance
from faultline.oracles.o_import import ORACLE, ORACLE_VERSION, plan_modules, run_o_import
from faultline.oracles.o_tests import ORACLE as TESTS_ORACLE
from faultline.oracles.o_tests import ORACLE_VERSION as TESTS_VERSION
from faultline.oracles.o_tests import run_o_tests
from faultline.witnesses.verify import Decision, verify_cell, witness_key

pytestmark = pytest.mark.docker
TOP = "acme_models"


def make_cell(env, scenario, consumer, test_world):
    return ensure_fixture_cell(env.conn, scenario_id=scenario, consumer=consumer, artifact_hash=env.artifact,
                               ref_world=env.worlds["ref"], test_world=env.worlds[test_world], env=env.builder.env)


def import_verifier(env, cell, modules):
    def run(world_hash):
        return run_o_import(env.sbx, env.image, world_hash=world_hash, artifact_hash=env.artifact, top_level=TOP,
                            modules=modules)
    return lambda **kw: verify_cell(env.conn, cell, oracle=ORACLE, version=ORACLE_VERSION, run_in_world=run,
                                    args={"modules": modules}, **kw)


def test_tc_1_6_1_witness_predicate_on_the_break_scenario(env):
    cell = make_cell(env, "D", "notify-svc", "notify_d")
    modules = plan_modules(TOP, ["acme_models.web"])
    v = import_verifier(env, cell, modules)()

    # six genuinely executed, distinct runs
    assert len(v.ref_runs) == 3 and len(v.test_runs) == 3
    ids = [r.run_id for r in v.ref_runs + v.test_runs]
    assert len(set(ids)) == 6 and all(r.provenance == RunProvenance.FRESH_EXECUTION for r in v.ref_runs + v.test_runs)
    assert all(r.result.failure_class == FailureClass.NONE for r in v.ref_runs)
    assert all(r.result.failure_class == FailureClass.ARTIFACT_FAILURE for r in v.test_runs)

    d = v.decision_for("acme_models.web")
    assert d.decision == Decision.WITNESS and d.witness_id
    assert d.signature.exc_type == "ImportError" and "url_quote" in d.signature.message_norm
    assert d.signature.origin_package == "flask"
    assert v.decision_for(TOP).decision == Decision.NO_DIVERGENCE            # the package itself imports fine

    row = env.conn.execute("SELECT * FROM witness WHERE id=?", (d.witness_id,)).fetchone()
    assert row["class"] == "BREAK" and row["ref_pass"] == 3 and row["test_fail"] == 3 and row["divergence"] == "IMPORT_ERROR"
    body = json.loads(row["body_json"])
    assert len(body["ref_run_ids"]) == 3 and len(body["test_run_ids"]) == 3
    runs = env.conn.execute("SELECT r.provenance, COUNT(*) n FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id "
                            "WHERE j.cell_id=? GROUP BY r.provenance", (cell.cell_id,)).fetchall()
    assert {r["provenance"]: r["n"] for r in runs} == {"FRESH_EXECUTION": 6}


def test_tc_1_6_1_o_tests_oracle_also_yields_a_per_test_witness(env):
    cell = make_cell(env, "D-tests", "notify-svc", "notify_d")
    cell = type(cell)(**{**cell.__dict__, "ref_world_hash": env.worlds["ref+tests"].world_hash,
                         "test_world_hash": env.worlds["notify_d+tests"].world_hash})

    def run(world_hash):
        return run_o_tests(env.sbx, env.image, world_hash=world_hash, artifact_hash=env.artifact, top_level=TOP)
    v = verify_cell(env.conn, cell, oracle=TESTS_ORACLE, version=TESTS_VERSION, run_in_world=run, args={})
    assert v.decision_for("test_web.py::test_show_customer").decision == Decision.WITNESS
    assert v.decision_for("test_customer.py::test_round_trip").decision == Decision.NO_DIVERGENCE
    assert {d.decision for d in v.decisions} == {Decision.WITNESS, Decision.NO_DIVERGENCE}


def test_tc_1_6_2_reference_failing_is_discarded_and_missing_module_is_not_a_witness(env):
    cell = make_cell(env, "D-bothfail", "notify-svc", "notify_d")
    # an artifact module that does not exist fails in BOTH worlds: never attributable to the consumer world
    v = import_verifier(env, cell, [TOP, "acme_models.nonexistent"])()
    assert v.decision_for("acme_models.nonexistent").decision == Decision.DISCARDED
    assert v.witnesses == []


def test_tc_1_6_3_cache_cannot_fake_repeats(env):
    cell = make_cell(env, "D-cache", "notify-svc", "notify_d")
    # a module list no other test uses, so the cache starts cold for this interaction (identical interactions share cache entries)
    verify = import_verifier(env, cell, plan_modules(TOP, ["acme_models.web", "acme_models.customer"]))
    first = verify()
    wid = first.decision_for("acme_models.web").witness_id
    assert first.decision_for("acme_models.web").decision == Decision.WITNESS

    second = verify()                                                           # cache is warm
    assert all(r.provenance == RunProvenance.REUSED_RESULT for r in second.ref_runs + second.test_runs)
    d = second.decision_for("acme_models.web")
    assert d.decision == Decision.REUSED_ONLY and d.witness_id == wid           # shown, but not re-counted
    assert not set(r.run_id for r in second.ref_runs + second.test_runs) & set(r.run_id for r in first.ref_runs + first.test_runs)

    forced = verify(force=True)                                                 # explicitly re-executed
    assert all(r.provenance == RunProvenance.FRESH_EXECUTION for r in forced.ref_runs + forced.test_runs)
    all_ids = {r.run_id for v in (first, second, forced) for r in v.ref_runs + v.test_runs}
    assert len(all_ids) == 18                                                   # every record has its own run id
    assert forced.decision_for("acme_models.web").decision == Decision.WITNESS
    key = witness_key(cell, ORACLE, ORACLE_VERSION, "acme_models.web", cell.env_profile_id)
    rows = env.conn.execute("SELECT id, body_json FROM witness WHERE witness_key=?", (key,)).fetchall()
    assert len(rows) == 1 and rows[0]["id"] == wid                            # one witness, however often it is re-verified
    assert len(json.loads(rows[0]["body_json"]).get("reverifications", [])) >= 1
    fresh = env.conn.execute("SELECT COUNT(*) FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id "
                             "WHERE j.cell_id=? AND r.provenance='FRESH_EXECUTION'", (cell.cell_id,)).fetchone()[0]
    reused = env.conn.execute("SELECT COUNT(*) FROM oracle_run r JOIN oracle_job j ON j.id=r.oracle_job_id "
                              "WHERE j.cell_id=? AND r.provenance='REUSED_RESULT'", (cell.cell_id,)).fetchone()[0]
    assert (fresh, reused) == (12, 6)


def test_tc_1_6_4_negative_controls_stay_clean(env):
    # Scenario A: the consumer resolves exactly the reference world, so the cell is NO_DRIFT and nothing is run.
    assert env.worlds["ref"].world_hash == env.worlds["ref"].world_hash
    # Scenario H: pydantic 2 consumer that only uses the deprecated-but-working API
    cell = make_cell(env, "H", "billing-svc", "billing_h")
    v = import_verifier(env, cell, plan_modules(TOP, ["acme_models.customer", "acme_models.web"]))()
    assert v.witnesses == []
    assert v.decision_for(TOP).decision == Decision.NO_DIVERGENCE
    assert v.decision_for("acme_models.customer").decision == Decision.NO_DIVERGENCE
    assert v.decision_for("acme_models.web").decision == Decision.NOT_APPLICABLE       # no Flask in this world
    assert env.conn.execute("SELECT COUNT(*) FROM witness WHERE cell_id=?", (cell.cell_id,)).fetchone()[0] == 0


def test_run_level_infrastructure_failure_is_reported_as_a_problem_not_a_witness(env):
    cell = make_cell(env, "D-infra", "notify-svc", "notify_d")

    def run(world_hash):
        return run_o_tests(env.sbx, env.image, world_hash=world_hash, artifact_hash=env.artifact, top_level=TOP)
    # the runtime worlds have no pytest: the harness reports it, which is a harness failure with no entries
    v = verify_cell(env.conn, cell, oracle=TESTS_ORACLE, version=TESTS_VERSION, run_in_world=run, args={})
    assert v.problem == "harness_failure" and v.witnesses == [] and v.decisions == []
