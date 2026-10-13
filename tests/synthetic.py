"""Builds a complete witness in a database without Docker, from synthetic oracle runs. Used by evidence-bundle tests."""
from pathlib import Path
from types import SimpleNamespace

from faultline.analysis.fixture import ensure_fixture_cell
from faultline.core.enums import Ecosystem, FailureClass, RunProvenance, WorldKind
from faultline.core.hashing import env_profile_id, world_hash
from faultline.core.ids import new_id
from faultline.core.models import (
    EntryOutcome,
    EnvProfile,
    OracleRunResult,
    ResolvedWorld,
    Runtime,
    WorldEntry,
)
from faultline.storage.store import Store
from faultline.witnesses.verify import verify_cell

ENV = EnvProfile(image_ref="sha256:" + "e" * 64)
RUNTIME = Runtime(name="cpython", version="3.12.15")


def make_world(kind, versions: dict[str, str]) -> ResolvedWorld:
    entries = tuple(WorldEntry(locator=n, name=n, version=v, artifact_sha256=("%064x" % (abs(hash((n, v))) % 16**64)))
                    for n, v in sorted(versions.items()))
    env_id = env_profile_id(ENV)
    draft = {"ecosystem": "pypi", "runtime": RUNTIME.model_dump(mode="json"), "env_profile_id": env_id, "entries": entries}
    return ResolvedWorld(world_hash=world_hash(draft), ecosystem=Ecosystem.PYPI, kind=kind, runtime=RUNTIME,
                         env_profile_id=env_id, entries=entries)


def result(passed: bool, stdout: str = ""):
    e = EntryOutcome(entry="acme_models.web", passed=passed, exc_type=None if passed else "ImportError",
                     message=None if passed else "cannot import name 'url_quote' from 'werkzeug.urls'",
                     frames=() if passed else ({"module": "flask.app", "line": 30, "func": "<module>"},),
                     failure_class=F_NONE if passed else FailureClass.ARTIFACT_FAILURE)
    return OracleRunResult(job_id="oj", run_id=new_id("run"), provenance=RunProvenance.FRESH_EXECUTION, exit_code=0,
                           duration_ms=5, failure_class=FailureClass.NONE if passed else FailureClass.ARTIFACT_FAILURE,
                           entries=(e,), stdout_tail=stdout, stderr_tail="", data={"python": "3.12.15"})


F_NONE = FailureClass.NONE


def make_witness(conn, tmp_path: Path, stdout_in_failure: str = ""):
    store = Store(tmp_path / "store")
    art_hash = "a_" + "1" * 40
    tree = store.artifact_dir(art_hash)
    (tree / "src" / "acme_models").mkdir(parents=True)
    (tree / "src" / "acme_models" / "__init__.py").write_text("v = 1\n", encoding="utf-8")
    ref = make_world(WorldKind.REFERENCE, {"flask": "2.2.2", "werkzeug": "2.2.3"})
    test = make_world(WorldKind.PROJECTED, {"flask": "2.2.2", "werkzeug": "3.0.6"})
    cell = ensure_fixture_cell(conn, scenario_id="S", consumer="notify-svc", artifact_hash=art_hash,
                               ref_world=ref, test_world=test, env=ENV)
    v = verify_cell(conn, cell, oracle="o_import", version="1.0.0",
                    run_in_world=lambda wh: result(wh == ref.world_hash, "" if wh == ref.world_hash else stdout_in_failure),
                    args={"modules": ["acme_models.web"]})
    wid = v.decision_for("acme_models.web").witness_id
    assert wid, v.decisions
    return SimpleNamespace(wid=wid, store=store, cell=cell, ref=ref, test=test, verification=v)
