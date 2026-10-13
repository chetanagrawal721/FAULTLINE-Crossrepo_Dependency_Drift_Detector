"""M1.7: evidence bundle v1 (TC-1.7.1 to TC-1.7.3). No Docker: the witness is built from synthetic oracle runs."""
import json
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from faultline.witnesses import bundle as B
from faultline.witnesses.bundle import verify_bundle, write_bundle
from tests.synthetic import make_witness

SCHEMA = json.loads((Path(B.__file__).resolve().parents[3] / "docs" / "schemas" / "evidence-bundle-v1.json").read_text())


@pytest.fixture
def exported(conn, tmp_path):
    w = make_witness(conn, tmp_path)
    info = write_bundle(conn, w.wid, tmp_path / "out" / "bundle.zip", w.store, created_at="2026-10-13T00:00:00Z")
    return w, info


def rewrite(src: Path, dst: Path, edit):
    """Copy a bundle, letting `edit(files: dict[name, bytes])` change it (the manifest is NOT re-hashed)."""
    with zipfile.ZipFile(src) as z:
        files = {i.filename: z.read(i.filename) for i in z.infolist()}
    edit(files)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return dst


def test_tc_1_7_1_bundle_validates_against_the_schema_and_carries_a_version(exported):
    _w, info = exported
    with zipfile.ZipFile(info.path) as z:
        manifest = json.loads(z.read("manifest.json"))
    assert manifest["schema_version"] == "1" and manifest["kind"] == "faultline-evidence-bundle"
    assert list(Draft202012Validator(SCHEMA).iter_errors(manifest)) == []
    names = {f["path"] for f in manifest["files"]}
    for required in ("witness.json", "plan/oracle_plan.json", "worlds/reference.world.json", "worlds/consumer.world.json",
                     "worlds/reference.lock.txt", "worlds/consumer.lock.txt", "env/env_profile.json", "README.md",
                     "REPRODUCE.md", "artifact/SOURCE.txt", "artifact/tree/src/acme_models/__init__.py"):
        assert required in names, required
    assert {n for n in names if n.startswith("runs/")} == {f"runs/{s}-{i}.json" for s in ("ref", "test") for i in (1, 2, 3)}
    assert manifest["run_summary"] == {"reference_passes": 3, "consumer_failures": 3, "all_fresh": True,
                                       "signature": manifest["run_summary"]["signature"]}
    assert manifest["claim"]["not_claimed"]
    res = verify_bundle(info.path)
    assert res.ok, res.errors


def test_bundle_contents_are_what_the_witness_says(exported):
    w, info = exported
    with zipfile.ZipFile(info.path) as z:
        ref = json.loads(z.read("worlds/reference.world.json"))
        lock = z.read("worlds/consumer.lock.txt").decode()
        runs = [json.loads(z.read(f"runs/test-{i}.json")) for i in (1, 2, 3)]
    assert ref["world_hash"] == w.ref.world_hash and {e["name"] for e in ref["entries"]} == {"flask", "werkzeug"}
    assert "Werkzeug==3.0.6".lower() in lock.lower() and "--hash=sha256:" in lock
    assert all(r["failure_class"] == "ARTIFACT_FAILURE" and r["provenance"] == "FRESH_EXECUTION" for r in runs)
    assert len({r["run_id"] for r in runs}) == 3


def test_same_content_gives_identical_bytes(conn, tmp_path):
    w = make_witness(conn, tmp_path)
    a = write_bundle(conn, w.wid, tmp_path / "a.zip", w.store, created_at="2026-10-13T00:00:00Z")
    b = write_bundle(conn, w.wid, tmp_path / "b.zip", w.store, created_at="2026-10-13T00:00:00Z")
    assert a.sha256 == b.sha256 and a.bundle_id == b.bundle_id


def test_tc_1_7_2_one_changed_byte_is_detected_and_the_file_is_named(exported, tmp_path):
    _w, info = exported

    def flip(files):
        d = bytearray(files["runs/test-1.json"])
        d[10] ^= 0x01
        files["runs/test-1.json"] = bytes(d)
    res = verify_bundle(rewrite(info.path, tmp_path / "t.zip", flip))
    assert not res.ok and res.errors == ["modified file (sha256 differs): runs/test-1.json"]


def test_tampered_manifest_and_changed_witness_are_rejected(exported, tmp_path):
    _w, info = exported

    def edit_manifest(files):
        m = json.loads(files["manifest.json"])
        m["witness_class"] = "SILENT_DIVERGENCE"
        m["witness_key"] = "not-a-key"
        files["manifest.json"] = json.dumps(m).encode()
    assert not verify_bundle(rewrite(info.path, tmp_path / "m.zip", edit_manifest)).ok

    def edit_witness(files):
        files["witness.json"] = files["witness.json"].replace(b"BREAK", b"FINE!")
    res = verify_bundle(rewrite(info.path, tmp_path / "w.zip", edit_witness))
    assert any("witness.json" in e for e in res.errors)


def test_missing_extra_duplicate_and_unsafe_entries_are_rejected(exported, tmp_path):
    _w, info = exported

    res = verify_bundle(rewrite(info.path, tmp_path / "1.zip", lambda f: f.pop("runs/ref-2.json")))
    assert res.errors == ["missing file: runs/ref-2.json"]

    res = verify_bundle(rewrite(info.path, tmp_path / "2.zip", lambda f: f.update({"notes.txt": b"smuggled"})))
    assert res.errors == ["file not listed in the manifest: notes.txt"]

    # (zipfile itself rewrites backslashes to slashes, so that case is covered by 'not listed in the manifest')
    for bad in ("../escape.txt", "/abs.txt", "a/../../b.txt", "C:/x.txt"):
        res = verify_bundle(rewrite(info.path, tmp_path / "3.zip", lambda f, bad=bad: f.update({bad: b"x"})))
        assert not res.ok and any("unsafe path" in e for e in res.errors), bad

    dup = tmp_path / "dup.zip"
    with zipfile.ZipFile(info.path) as src, zipfile.ZipFile(dup, "w") as z, pytest.warns(UserWarning):
        for i in src.infolist():
            z.writestr(i.filename, src.read(i.filename))
        z.writestr("README.md", b"second copy")
    assert any("duplicate" in e for e in verify_bundle(dup).errors)


def test_unknown_schema_version_not_a_zip_and_oversize_are_rejected(exported, tmp_path, monkeypatch):
    _w, info = exported

    def bump(files):
        m = json.loads(files["manifest.json"])
        m["schema_version"] = "2"
        files["manifest.json"] = json.dumps(m).encode()
    res = verify_bundle(rewrite(info.path, tmp_path / "v.zip", bump))
    assert not res.ok and "unsupported schema_version" in res.errors[0]

    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"this is not a zip")
    assert not verify_bundle(junk).ok

    monkeypatch.setattr(B, "MAX_FILE_BYTES", 100)
    assert any("larger than" in e for e in verify_bundle(info.path).errors)


def test_consistency_checks_catch_a_bundle_whose_hashes_were_recomputed_but_content_lies(exported, tmp_path):
    """An attacker who also fixes the manifest hashes still cannot make a non-fresh or short run set verify."""
    _w, info = exported

    def lie(files):
        r = json.loads(files["runs/test-1.json"])
        r["provenance"] = "REUSED_RESULT"
        files["runs/test-1.json"] = B._jdump(r)
        m = json.loads(files["manifest.json"])
        for f in m["files"]:
            if f["path"] == "runs/test-1.json":
                f["sha256"], f["size"] = B.content_hash(files["runs/test-1.json"]), len(files["runs/test-1.json"])
        files["manifest.json"] = B._jdump(m)
    res = verify_bundle(rewrite(info.path, tmp_path / "lie.zip", lie))
    assert not res.ok and any("not a fresh execution" in e for e in res.errors)


def test_tc_1_7_3_no_secrets_in_the_bundle(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("FAULTLINE_ADMIN_TOKEN", "canary-admin-token-7f3a91")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_" + "Z" * 36)
    monkeypatch.setenv("SOME_SECRET", "another-canary-value-55")
    leaked = "boom canary-admin-token-7f3a91 and ghp_" + "Z" * 36 + " and another-canary-value-55 and Bearer " + "abcdefghijklmnop" + "12345"
    w = make_witness(conn, tmp_path, stdout_in_failure=leaked)
    info = write_bundle(conn, w.wid, tmp_path / "b.zip", w.store)
    with zipfile.ZipFile(info.path) as z:
        blob = b"".join(z.read(n) for n in z.namelist()).decode("utf-8", "replace")
    for canary in ("canary-admin-token-7f3a91", "ghp_" + "Z" * 36, "another-canary-value-55", "abcdefghijklmnop" + "12345"):
        assert canary not in blob, canary
    assert "[REDACTED]" in blob                                           # it was in the run output and was scrubbed
    assert verify_bundle(info.path).ok


def test_a_witness_without_three_fresh_runs_cannot_be_exported(conn, tmp_path):
    w = make_witness(conn, tmp_path)
    conn.execute("UPDATE oracle_run SET provenance='REUSED_RESULT' WHERE id IN (SELECT id FROM oracle_run LIMIT 1)")
    with pytest.raises(B.BundleError):
        write_bundle(conn, w.wid, tmp_path / "x.zip", w.store)


def test_a_decompression_bomb_is_rejected_before_anything_is_read(exported, tmp_path):
    """TC-11.3.3: a few kilobytes that expand to far beyond the ratio limit."""
    _w, info = exported
    bomb = tmp_path / "bomb.zip"
    with zipfile.ZipFile(info.path) as src, zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            z.writestr(i.filename, src.read(i.filename))
        z.writestr("filler.bin", b"\0" * 5_000_000)                    # ~5 KB compressed, 5 MB expanded
    res = verify_bundle(bomb)
    assert not res.ok and any("suspicious compression ratio" in e for e in res.errors)


def test_symlink_and_device_entries_in_a_bundle_are_rejected(exported, tmp_path):
    """TC-11.3.3: a zip can carry a symbolic link; extracting one could point outside the work directory."""
    _w, info = exported
    link = tmp_path / "link.zip"
    with zipfile.ZipFile(info.path) as src, zipfile.ZipFile(link, "w", zipfile.ZIP_DEFLATED) as z:
        for i in src.infolist():
            z.writestr(i.filename, src.read(i.filename))
        zi = zipfile.ZipInfo("provenance/evil-link")
        zi.create_system = 3
        zi.external_attr = (0o120777 << 16)                            # a symlink to wherever its content says
        z.writestr(zi, "/etc/passwd")
    res = verify_bundle(link)
    assert not res.ok and any("special file entries" in e for e in res.errors)
