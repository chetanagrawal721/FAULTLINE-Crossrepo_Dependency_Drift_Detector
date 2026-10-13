"""M4.2: exact projection, consumer-import scan and the reference-failure policy."""
import json

import pytest

from faultline.core.scenario import load_scenario
from faultline.resolvers.pinned import parse_pinned_lock
from faultline.usage.consumer_imports import artifact_modules, scan_imports
from faultline.worlds.projection import project
from faultline.worlds.reference import ReferenceFailure, ReferenceWorld, select_reference
from tests.livefix import FIXTURES, fixture_repo

ROOT = FIXTURES.parents[1]


def ref_world(world_hash="w_ref"):
    text = (FIXTURES / "acme-models" / "requirements.lock.txt").read_text(encoding="utf-8")
    return ReferenceWorld("p", world_hash, tuple(parse_pinned_lock(text)), "lockfile")


def lock_of(path):
    return parse_pinned_lock((FIXTURES / path / "requirements.lock.txt").read_text(encoding="utf-8"))


@pytest.mark.parametrize("scenario", ["A", "D", "H"])
def test_tc_4_2_1_projection_equals_the_scenario_yaml_exactly(scenario):
    sc = load_scenario(ROOT / "fixtures" / "scenarios" / f"{scenario}.yaml")
    ref = ref_world()
    cells = {c.consumer: c for c in sc.expect.cells}
    for c in sc.consumers:
        proj = project(ref, lock_of(c.path.removeprefix("fixtures/repos/")))
        expected = cells[c.repo]
        if expected.state == "NO_DRIFT":
            assert proj.no_drift and proj.delta == ()
        else:
            assert sorted(d.name for d in proj.delta) == sorted(expected.delta), (scenario, c.repo)
    if scenario == "D":
        d = project(ref, lock_of("notify-svc/D")).delta
        assert {x.name: (x.reference, x.consumer) for x in d}["werkzeug"][0] == "2.2.3"      # the reference value, exactly


def test_equal_consumers_share_a_projection_key_and_different_ones_do_not():
    ref = ref_world()
    a, b = project(ref, lock_of("orders-svc/A")), project(ref, lock_of("orders-svc/A"))
    assert a.key == b.key and a.no_drift
    assert project(ref, lock_of("notify-svc/D")).key != a.key


def test_tc_4_2_2_consumer_import_scan_lists_exactly_the_modules_imported(tmp_path):
    prod = fixture_repo("acme-models")
    entries = [{"path": k, "kind": "file", "size": len(v)} for k, v in prod.items()]
    known = artifact_modules(tmp_path, entries, "src", "acme_models")
    assert known == {"acme_models", "acme_models.customer", "acme_models.settings", "acme_models.web"}   # settings was added to the shared fixture for scenario B
    consumer = {"app/a.py": "import acme_models.customer as c\nfrom acme_models.web import make_app\n",
                "app/b.py": "from acme_models import customer\nimport json\n", "app/c.py": "import importlib\nimportlib.import_module(name)\nimportlib.import_module('acme_models.customer')\n",
                "node_modules/x/y.py": "import acme_models.web\n", "tests/test_x.py": "import acme_models\n"}
    for k, v in consumer.items():
        (tmp_path / k).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / k).write_text(v)
    ents = [{"path": k, "kind": "file", "size": len(v)} for k, v in consumer.items()]
    scan = scan_imports(tmp_path, ents, "acme_models", known)
    assert scan.modules == ["acme_models", "acme_models.customer", "acme_models.web"]
    only = scan_imports(tmp_path, [e for e in ents if e["path"] in ("app/b.py",)], "acme_models", known)
    assert only.modules == ["acme_models", "acme_models.customer"]                                        # `from acme_models import customer`
    assert [d["line"] for d in scan.dynamic] == [2]                                         # the non-literal import is recorded as dynamic
    two = scan_imports(tmp_path, [e for e in ents if e["path"] == "app/a.py"], "acme_models", known)
    assert two.modules == ["acme_models.customer", "acme_models.web"]
    assert all(s["file"] != "node_modules/x/y.py" for s in scan.sites)                     # ignored directories are not scanned


@pytest.mark.docker
def test_tc_4_2_2_a_module_needing_an_absent_extra_is_not_applicable(sbx, image, daemon):
    from faultline.core.enums import WorldKind
    from faultline.oracles.artifacts import prepare_artifact
    from faultline.oracles.o_import import run_o_import
    from faultline.worlds.builder import WorldBuilder
    b = WorldBuilder(sbx, image)
    text = (FIXTURES / "billing-svc" / "H" / "requirements.lock.txt").read_text(encoding="utf-8")
    world = b.materialize(text, WorldKind.PROJECTED)
    assert b.build(world, text).status in ("BUILT", "REUSED")
    art = prepare_artifact(FIXTURES / "acme-models", daemon.store)
    run = run_o_import(sbx, image, world_hash=world.world_hash, artifact_hash=art, top_level="acme_models",
                       modules=["acme_models", "acme_models.customer", "acme_models.web"])
    by = {e.entry: e for e in run.entries}
    assert by["acme_models.customer"].passed and by["acme_models.web"].not_applicable and not by["acme_models.web"].passed


# ---------------------------------------------------------------------------- TC-4.2.3 reference failure policy

REASONS = ["no_manifest", "needs_build", "non_registry_source", "private_index_without_lock", "setup_py_not_executed"]


@pytest.mark.parametrize("reason", REASONS)
def test_tc_4_2_3_reference_failures_are_inconclusive_with_provenance(conn, reason):
    from tests.reffix import failing_project
    pid = failing_project(conn, reason)
    out = select_reference(conn, pid)
    assert isinstance(out, ReferenceFailure) and out.reason == reason and out.text
    assert out.provenance["failure"]["reason"] == reason and out.provenance["cutoff"]


def test_unresolved_and_partial_references_are_failures_too(conn):
    from tests.reffix import failing_project, partial_project
    assert select_reference(conn, "prj_nothing").reason == "not_resolved"
    assert select_reference(conn, partial_project(conn)).reason == "private_packages"
    assert isinstance(select_reference(conn, failing_project(conn, "lock_unsupported")), ReferenceFailure)
    assert json.dumps(select_reference(conn, "prj_nothing").provenance) == "{}"
