"""M5.2: replay a real witness bundle: exact reproduction, environment-limited, non-reproducible, and never from moving refs."""
import json
import zipfile
from pathlib import Path

import pytest

from faultline.core.hashing import content_hash, object_hash
from faultline.witnesses.bundle import verify_bundle, write_bundle
from faultline.witnesses.replay import ReplayOutcome, ReplayRefused, replay
from tests.integration.test_live import d_scenario  # noqa: F401  (module-scoped real analysis of scenario D)

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def bundle(d_scenario, daemon, tmp_path_factory):  # noqa: F811
    conn, res, ids = d_scenario
    wid = conn.execute("SELECT id FROM witness WHERE oracle='o_import' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    info = write_bundle(conn, wid, tmp_path_factory.mktemp("b") / "witness.zip", daemon.store, mode="LIVE")
    return info.path


class Recording:
    """Wraps a SandboxClient and records every harness script used."""

    def __init__(self, sbx):
        self.sbx, self.scripts = sbx, []

    def submit(self, spec):
        self.scripts.append(spec.get("script"))
        return self.sbx.submit(spec)

    def __getattr__(self, name):
        return getattr(self.sbx, name)


def rewrite(src: Path, dst: Path, edit) -> Path:
    """Copy a bundle, edit file contents, and RE-HASH the manifest so the bundle is internally valid."""
    with zipfile.ZipFile(src) as z:
        files = {i.filename: z.read(i.filename) for i in z.infolist()}
    edit(files)
    m = json.loads(files["manifest.json"])
    for f in m["files"]:
        if f["path"] in files:
            f["sha256"], f["size"] = content_hash(files[f["path"]]), len(files[f["path"]])
    m["bundle_id"] = "bdl_" + object_hash([f["sha256"] for f in m["files"]])[:24]
    files["manifest.json"] = (json.dumps(m, indent=2, sort_keys=True) + "\n").encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return dst


def test_the_bundle_carries_pinned_provenance_verdict_and_attribution(bundle):
    with zipfile.ZipFile(bundle) as z:
        names = set(z.namelist())
        pinned = json.loads(z.read("provenance/pinned.json"))
        verdict = json.loads(z.read("provenance/verdict.json"))
        att = json.loads(z.read("attribution/attribution.json"))
    assert verify_bundle(bundle).ok
    assert {r["role"] for r in pinned["repositories"]} == {"artifact", "consumer"} and all(len(r["commit"]) == 40 for r in pinned["repositories"])
    assert any(n.startswith("sources/faultline-demo/notify-svc@") and n.endswith("requirements.lock.txt") for n in names)
    assert verdict["verdict"] == "BREAK_WITNESSED" and verdict["policy_version"] == "verdict-policy/1" and "3 fresh reference passes" in verdict["predicate"]
    assert att["minimal_set"] == ["werkzeug"] and att["attempts"] and "forced world" in att["label"]


def test_tc_5_2_1_replay_refuses_every_kind_of_bad_bundle(bundle, tmp_path):
    def mutate(kind):
        def edit(files):
            if kind == "missing":
                files.pop("runs/ref-1.json")
            elif kind == "byte":
                d = bytearray(files["runs/test-1.json"])
                d[10] ^= 1
                files["runs/test-1.json"] = bytes(d)
            elif kind == "path":
                files["../escape.txt"] = b"x"
            elif kind == "schema":
                m = json.loads(files["manifest.json"])
                m["schema_version"] = "9"
                files["manifest.json"] = json.dumps(m).encode()
        return edit
    for kind in ("missing", "byte", "path", "schema"):
        with zipfile.ZipFile(bundle) as z:
            files = {i.filename: z.read(i.filename) for i in z.infolist()}
        mutate(kind)(files)
        bad = tmp_path / f"{kind}.zip"
        with zipfile.ZipFile(bad, "w") as z:
            for n, d in files.items():
                z.writestr(n, d)
        with pytest.raises(ReplayRefused) as ei:
            replay(bad, None, "img", None)                                     # no sandbox, no store: nothing may be touched
        assert ei.value.errors, kind
    dup = tmp_path / "dup.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(dup, "w") as z, pytest.warns(UserWarning):
        for i in src.infolist():
            z.writestr(i.filename, src.read(i.filename))
        z.writestr("README.md", b"again")
    with pytest.raises(ReplayRefused):
        replay(dup, None, "img", None)


def test_replay_on_the_same_machine_is_an_exact_reproduction(bundle, d_scenario, daemon, image):  # noqa: F811
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    sbx = Recording(SandboxClient(port=daemon.port, token=TOKEN, timeout=600))
    res = replay(bundle, sbx, image, daemon.store)
    assert res.outcome == ReplayOutcome.EXACT_REPRODUCTION, res.reasons
    assert (res.reference_passes, res.consumer_failures, res.signature_matches) == (3, 3, True)
    assert set(sbx.scripts) <= {"fetch_wheels.py", "build_world.py", "o_import.py", "world_info.py"}      # no repository fetch of any kind
    assert "fetch_repo.py" not in sbx.scripts and res.fetched_by_moving_ref is False


def test_tc_5_2_3_a_missing_artifact_is_restored_from_the_bundle_never_fetched(bundle, d_scenario, daemon, image):  # noqa: F811
    import shutil

    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN
    manifest = verify_bundle(bundle).manifest
    cached = daemon.store.artifact_dir(manifest["artifact"]["content_hash"])
    shutil.rmtree(cached, ignore_errors=True)                                   # delete the artifact from this machine's cache
    sbx = Recording(SandboxClient(port=daemon.port, token=TOKEN, timeout=600))
    res = replay(bundle, sbx, image, daemon.store)
    assert any("missing from this machine's store and was restored from the bundle" in r for r in res.reasons)
    assert cached.exists() and "fetch_repo.py" not in sbx.scripts and res.outcome == ReplayOutcome.EXACT_REPRODUCTION


def test_a_tampered_but_rehashed_artifact_tree_is_non_reproducible_and_names_the_hash(bundle, daemon, image, tmp_path):
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN

    def edit(files):
        k = next(n for n in files if n.startswith("artifact/tree/") and n.endswith("web.py"))
        files[k] = files[k] + b"\n# tampered\n"
    bad = rewrite(bundle, tmp_path / "t.zip", edit)
    assert verify_bundle(bad).ok                                                # internally consistent: only the content hash catches it
    res = replay(bad, SandboxClient(port=daemon.port, token=TOKEN, timeout=600), image, daemon.store)
    assert res.outcome == ReplayOutcome.NON_REPRODUCIBLE and "does not match its content hash" in res.reasons[0]


def test_a_different_environment_image_is_environment_limited(bundle, daemon, image, tmp_path):
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN

    def edit(files):
        e = json.loads(files["env/env_profile.json"])
        e["image_ref"] = "sha256:" + "0" * 64
        files["env/env_profile.json"] = (json.dumps(e, indent=2, sort_keys=True) + "\n").encode()
    res = replay(rewrite(bundle, tmp_path / "e.zip", edit), SandboxClient(port=daemon.port, token=TOKEN, timeout=600), image, daemon.store)
    assert res.outcome == ReplayOutcome.ENVIRONMENT_LIMITED and any("execution image differs" in r for r in res.reasons)


def test_a_witness_that_no_longer_reproduces_is_non_reproducible(bundle, daemon, image, tmp_path):
    from faultline.sandbox.client import SandboxClient
    from tests.conftest import TOKEN

    def edit(files):
        w = json.loads(files["witness.json"])
        w["signature"]["message_norm"] = "a different failure message"
        files["witness.json"] = (json.dumps(w, indent=2, sort_keys=True) + "\n").encode()
    res = replay(rewrite(bundle, tmp_path / "n.zip", edit), SandboxClient(port=daemon.port, token=TOKEN, timeout=600), image, daemon.store)
    assert res.outcome == ReplayOutcome.NON_REPRODUCIBLE and res.signature_matches is False
