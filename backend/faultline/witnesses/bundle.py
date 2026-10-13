"""Evidence bundles: a versioned, hash-checked zip that carries everything needed to inspect and re-run a witness.

write_bundle() exports one witness from the database. verify_bundle() is deliberately strict and independent of the
database: it is what a reviewer (or another machine) runs on a bundle it received. It rejects missing, modified,
duplicate, extra or path-traversal entries and anything larger than the limits, before anything is trusted.
"""
import json
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

from ..core.config import repo_root
from ..core.hashing import canonical_json, content_hash, object_hash
from ..resolvers.pinned import PinnedRequirement, render_lock
from ..security.scrub import scrub_obj, scrub_text
from ..storage.store import Store

SCHEMA_VERSION = "1"
SCHEMA_PATH = repo_root() / "docs" / "schemas" / "evidence-bundle-v1.json"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILES = 500
MAX_COMPRESSION_RATIO = 200
TAIL_CHARS = 4000
CLAIM = ("A specific interaction passed in the reference world and failed in the consumer world, reproducibly "
         "(3 fresh executions each, identical normalized failure signature), under the environment recorded here.")
NOT_CLAIMED = ["that the dependency upgrade is incompatible in general",
               "that other interactions, inputs or code paths are affected",
               "that the minimal cause is known (attribution is a separate result)"]


class BundleError(Exception):
    pass


@dataclass
class BundleInfo:
    path: Path
    bundle_id: str
    sha256: str
    size: int
    files: int


@dataclass
class VerifyResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    manifest: dict | None = None


def _jdump(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load_world(conn: sqlite3.Connection, world_hash: str) -> dict:
    w = conn.execute("SELECT * FROM resolved_world WHERE world_hash=?", (world_hash,)).fetchone()
    if w is None:
        raise BundleError(f"world {world_hash} is not in the database")
    rows = conn.execute(
        "SELECT we.locator, we.scope, we.source_kind, pv.name, pv.version, pv.artifact_sha256 FROM world_entry we "
        "JOIN package_version pv ON pv.id = we.package_version_id WHERE we.world_hash=? ORDER BY we.locator",
        (world_hash,)).fetchall()
    return {"world_hash": world_hash, "ecosystem": w["ecosystem"], "kind": w["kind"], "runtime": json.loads(w["runtime_json"]),
            "env_profile_id": w["env_profile_id"],
            "entries": [{"locator": r["locator"], "name": r["name"], "version": r["version"], "scope": r["scope"],
                         "source_kind": r["source_kind"], "artifact_sha256": r["artifact_sha256"]} for r in rows]}


def _lock_text(world: dict) -> str:
    reqs = [PinnedRequirement(e["name"], e["name"], e["version"], (e["artifact_sha256"],) if e["artifact_sha256"] else ())
            for e in world["entries"]]
    return ("# Exact packages of this world, pinned to the wheel hash that was actually installed.\n" + render_lock(reqs))


def _run_file(conn: sqlite3.Connection, run_id: str) -> dict:
    r = conn.execute("SELECT r.*, j.side, j.world_hash, j.oracle, j.oracle_version, j.spec_json FROM oracle_run r "
                     "JOIN oracle_job j ON j.id = r.oracle_job_id WHERE r.id=?", (run_id,)).fetchone()
    if r is None:
        raise BundleError(f"run {run_id} is not in the database")
    res = json.loads(r["result_json"])
    return scrub_obj({
        "run_id": r["id"], "job_id": r["oracle_job_id"], "run_index": r["run_index"], "side": r["side"],
        "world_hash": r["world_hash"], "provenance": r["provenance"], "created_at": r["created_at"],
        "env_fingerprint": r["env_fingerprint"], "exit_code": r["exit_code"], "duration_ms": r["duration_ms"],
        "failure_class": r["failure_class"], "entries": res.get("entries", []),
        "stdout_tail": (res.get("stdout_tail") or "")[-TAIL_CHARS:], "stderr_tail": (res.get("stderr_tail") or "")[-TAIL_CHARS:],
        "truncated": bool(res.get("truncated")),
    })


def write_bundle(conn: sqlite3.Connection, witness_id: str, out_path: Path, store: Store, *, mode: str = "FIXTURE",
                 created_at: str | None = None) -> BundleInfo:
    wit = conn.execute("SELECT * FROM witness WHERE id=?", (witness_id,)).fetchone()
    if wit is None:
        raise BundleError(f"witness {witness_id} not found")
    body = json.loads(wit["body_json"])
    cell = conn.execute("SELECT * FROM cell WHERE id=?", (wit["cell_id"],)).fetchone()
    ref_w, test_w = _load_world(conn, cell["ref_world_hash"]), _load_world(conn, cell["test_world_hash"])
    env = conn.execute("SELECT * FROM env_profile WHERE id=?", (ref_w["env_profile_id"],)).fetchone()
    artifact_hash = conn.execute("SELECT p.artifact_content_hash FROM project p WHERE p.id=?",
                                 (cell["artifact_project_id"],)).fetchone()[0]
    runs = [_run_file(conn, rid) for rid in body["ref_run_ids"] + body["test_run_ids"]]
    job = conn.execute("SELECT spec_json FROM oracle_job WHERE id=?", (runs[0]["job_id"],)).fetchone()
    args = json.loads(job["spec_json"]) if job else {}
    bad = [r["run_id"] for r in runs if r["provenance"] != "FRESH_EXECUTION"]
    if bad or len(body["ref_run_ids"]) != 3 or len(body["test_run_ids"]) != 3:
        raise BundleError("a witness bundle needs exactly three fresh reference and three fresh consumer runs")

    files: dict[str, bytes] = {}
    files["witness.json"] = _jdump(scrub_obj({"witness": body, "signature": json.loads(wit["signature_json"]),
                                              "divergence": wit["divergence"]}))
    files["plan/oracle_plan.json"] = _jdump(scrub_obj({"oracle": wit["oracle"], "version": wit["oracle_version"],
                                                       "entry_point": wit["entry_point"], "args": args}))
    for r in runs:
        files[f"runs/{r['side']}-{r['run_index']}.json"] = _jdump(r)
    files["worlds/reference.world.json"] = _jdump(ref_w)
    files["worlds/consumer.world.json"] = _jdump(test_w)
    files["worlds/reference.lock.txt"] = _lock_text(ref_w).encode()
    files["worlds/consumer.lock.txt"] = _lock_text(test_w).encode()
    files["env/env_profile.json"] = _jdump(scrub_obj({"id": ref_w["env_profile_id"], "image_ref": env["image_ref"],
                                                      "arch": env["arch"], "locale": env["locale"], "tz": env["tz"],
                                                      "env": json.loads(env["env_json"]), "seed": env["seed"]}))
    src = store.artifact_dir(artifact_hash)
    for p in sorted(x for x in src.rglob("*") if x.is_file()):
        files[f"artifact/tree/{p.relative_to(src).as_posix()}"] = p.read_bytes()
    files["artifact/SOURCE.txt"] = (f"content_hash: {artifact_hash}\nThe tree under artifact/tree is the exact source that was tested.\n").encode()
    files.update(_provenance_files(conn, store, wit, cell, mode))
    files["README.md"] = _readme(wit, body, ref_w, test_w, artifact_hash).encode()
    files["REPRODUCE.md"] = _reproduce().encode()

    total = sum(len(v) for v in files.values())
    if len(files) + 1 > MAX_FILES or total > MAX_TOTAL_BYTES or any(len(v) > MAX_FILE_BYTES for v in files.values()):
        raise BundleError("bundle exceeds the size limits")

    listing = [{"path": p, "sha256": content_hash(b), "size": len(b)} for p, b in sorted(files.items())]
    created = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "schema_version": SCHEMA_VERSION, "kind": "faultline-evidence-bundle",
        "bundle_id": "bdl_" + object_hash([x["sha256"] for x in listing])[:24], "created_at": created, "mode": mode,
        "witness_id": witness_id, "witness_class": wit["class"], "witness_key": wit["witness_key"],
        "claim": {"statement": CLAIM, "not_claimed": NOT_CLAIMED},
        "oracle": {"name": wit["oracle"], "version": wit["oracle_version"], "entry_point": wit["entry_point"], "args": scrub_obj(args)},
        "artifact": {"content_hash": artifact_hash, "source_dir": "artifact/tree"},
        "worlds": {"reference": ref_w["world_hash"], "consumer": test_w["world_hash"], "env_profile": ref_w["env_profile_id"]},
        "run_summary": {"reference_passes": 3, "consumer_failures": 3, "all_fresh": True,
                        "signature": json.loads(wit["signature_json"])},
        "files": listing,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in [("manifest.json", _jdump(manifest))] + sorted(files.items()):
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))     # fixed timestamp: same content, same bytes
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data)
    raw = out_path.read_bytes()
    return BundleInfo(out_path, manifest["bundle_id"], content_hash(raw), len(raw), len(files) + 1)


def _provenance_files(conn: sqlite3.Connection, store: Store, wit, cell, mode: str) -> dict[str, bytes]:
    """Pinned SHAs, the manifests and lockfiles that were read, the verdict predicate with its policy version, and the attribution
    attempts. Everything here comes from persisted rows and from the immutable snapshots; nothing is fetched."""
    out: dict[str, bytes] = {}
    projects = [cell["artifact_project_id"]] + [r[0] for r in conn.execute("SELECT consumer_project_id FROM cell_consumer WHERE cell_id=?", (cell["id"],))]
    repos, copied = [], 0
    for pid in dict.fromkeys(projects):
        row = conn.execute("SELECT p.id, p.rel_path, s.sha, s.store_path, r.owner, r.name FROM project p JOIN snapshot s ON s.id=p.snapshot_id "
                           "JOIN repository r ON r.id=s.repository_id WHERE p.id=?", (pid,)).fetchone()
        if row is None:
            continue
        role = "artifact" if pid == cell["artifact_project_id"] else "consumer"
        slug = f"{row['owner']}/{row['name']}"
        repos.append({"role": role, "repository": slug, "commit": row["sha"], "project_path": row["rel_path"]})
        snap = store.snapshot_dir(row["store_path"]) if row["store_path"] and row["store_path"].replace("_", "").isalnum() else None
        if snap is not None and snap.exists():
            for m in conn.execute("SELECT path FROM manifest WHERE project_id=? ORDER BY path", (pid,)):
                f = snap / m["path"]
                if f.is_file() and f.stat().st_size < 1_000_000 and copied < 60:
                    out[f"sources/{slug}@{row['sha'][:10]}/{m['path']}"] = f.read_bytes()
                    copied += 1
    out["provenance/pinned.json"] = _jdump(scrub_obj({"mode": mode, "repositories": repos,
                                                       "note": "every file under sources/ was read at exactly this commit"}))
    fnd = conn.execute("SELECT verdict, headline, scope_json FROM finding WHERE cell_id=? ORDER BY created_at DESC LIMIT 1", (cell["id"],)).fetchone()
    scope = json.loads(fnd["scope_json"]) if fnd else {}
    out["provenance/verdict.json"] = _jdump(scrub_obj({
        "verdict": fnd["verdict"] if fnd else None, "headline": fnd["headline"] if fnd else None,
        "policy_version": scope.get("policy"), "oracle_plan": scope.get("oracle_plan"), "delta": scope.get("delta"),
        "not_checked": scope.get("not_checked"),
        "predicate": "3 fresh reference passes AND 3 fresh consumer failures, classified ARTIFACT_FAILURE, with one identical normalised signature"}))
    att = conn.execute("SELECT * FROM attribution WHERE witness_id=?", (wit["id"],)).fetchone()
    if att:
        attempts = [dict(a) for a in conn.execute("SELECT direction, subset_json, world_hash, outcome, note FROM attribution_attempt WHERE attribution_id=? ORDER BY seq", (att["id"],))]
        out["attribution/attribution.json"] = _jdump(scrub_obj({
            "status": att["status"], "sidedness": att["sidedness"], "minimal_set": json.loads(att["minimal_set_json"]), "runs": att["runs"],
            "notes": json.loads(att["notes_json"]), "attempts": attempts,
            "label": "attribution experiment (forced world): these worlds are experiments, not observed environments"}))
    return out


def _readme(wit, body, ref_w, test_w, artifact_hash) -> str:
    sig = json.loads(wit["signature_json"])
    return scrub_text(f"""# Faultline evidence bundle

This bundle records one **witness**: {CLAIM}

- Entry point: `{wit['entry_point']}` (oracle `{wit['oracle']}` {wit['oracle_version']})
- Failure: `{sig['exc_type']}`: {sig['message_norm']}
- Origin: `{sig.get('origin_module')}`
- Reference world: `{ref_w['world_hash']}`  Consumer world: `{test_w['world_hash']}`
- Artifact content hash: `{artifact_hash}`
- Runs: 3 reference passes and 3 consumer failures, all freshly executed (see `runs/`).

## What this does not claim
""" + "\n".join(f"- {x}" for x in NOT_CLAIMED) + """

## Checking it
Every file is listed in `manifest.json` with its sha256. Run `python -m faultline.witnesses.bundle <bundle.zip>`
to verify integrity and consistency. `REPRODUCE.md` explains how to re-run the witness.
""")


def _reproduce() -> str:
    return """# Re-running this witness

1. Verify the bundle: `python -m faultline.witnesses.bundle bundle.zip` (no network, no Docker needed).
2. The two worlds are fully described by `worlds/*.world.json` and `worlds/*.lock.txt` (exact versions and wheel hashes).
   Build each as a virtual environment from those wheels only (`pip install --no-deps --require-hashes -r <lock>`).
3. Put `artifact/tree/src` on `PYTHONPATH` and run the oracle in `plan/oracle_plan.json` in each world, three times,
   with network access disabled. Expect the reference to pass and the consumer to fail with the signature in `witness.json`.

Automated replay does these steps: `python -m faultline.witnesses.replay bundle.zip` (needs Docker and the Faultline sandbox).
It reports exactly one of EXACT_REPRODUCTION, ENVIRONMENT_LIMITED or NON_REPRODUCIBLE, with reasons. Wheels are fetched only by
sha256 from the lock files; nothing is ever fetched by branch or tag.
"""


# ----------------------------------------------------------------------------- verification

def _safe_name(name: str) -> bool:
    p = PurePosixPath(name)
    return not (name.startswith(("/", "\\")) or "\\" in name or ".." in p.parts or ":" in name.split("/")[0]
                or name == "" or "\x00" in name)


def verify_bundle(path: str | Path) -> VerifyResult:
    errors: list[str] = []
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        return VerifyResult(False, [f"not a readable zip file: {exc}"])
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        names = [i.filename for i in infos]
        if len(names) > MAX_FILES:
            return VerifyResult(False, [f"too many entries ({len(names)})"])
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            errors.append(f"duplicate entries: {dupes}")
        for i in infos:
            if not _safe_name(i.filename):
                errors.append(f"unsafe path in bundle: {i.filename!r}")
            if (i.external_attr >> 16) & 0o170000 in (0o120000, 0o060000, 0o020000, 0o010000):      # symlink, block or char device, fifo
                errors.append(f"{i.filename}: special file entries (links, devices) are not allowed")
            if i.file_size > MAX_FILE_BYTES:
                errors.append(f"{i.filename}: larger than {MAX_FILE_BYTES} bytes")
            if i.compress_size and i.file_size / max(i.compress_size, 1) > MAX_COMPRESSION_RATIO and i.file_size > 100_000:
                errors.append(f"{i.filename}: suspicious compression ratio")
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            errors.append("bundle is larger than the total size limit")
        if errors:
            return VerifyResult(False, errors)
        if "manifest.json" not in names:
            return VerifyResult(False, ["manifest.json is missing"])
        try:
            manifest = json.loads(z.read("manifest.json"))
        except ValueError as exc:
            return VerifyResult(False, [f"manifest.json is not valid JSON: {exc}"])
        if manifest.get("schema_version") != SCHEMA_VERSION:
            return VerifyResult(False, [f"unsupported schema_version {manifest.get('schema_version')!r} (supported: {SCHEMA_VERSION})"], manifest)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        for e in sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda x: list(x.path)):
            errors.append(f"manifest schema: {'/'.join(map(str, e.path)) or '<root>'}: {e.message}")
        if errors:
            return VerifyResult(False, errors, manifest)

        listed = {f["path"]: f for f in manifest["files"]}
        if len(listed) != len(manifest["files"]):
            errors.append("manifest lists a file more than once")
        for p in listed:
            if not _safe_name(p):
                errors.append(f"manifest lists an unsafe path: {p!r}")
        present = set(names) - {"manifest.json"}
        for p in sorted(set(listed) - present):
            errors.append(f"missing file: {p}")
        for p in sorted(present - set(listed)):
            errors.append(f"file not listed in the manifest: {p}")
        for p in sorted(set(listed) & present):
            data = z.read(p)
            if len(data) != listed[p]["size"]:
                errors.append(f"modified file (size differs): {p}")
            elif content_hash(data) != listed[p]["sha256"]:
                errors.append(f"modified file (sha256 differs): {p}")
        if errors:
            return VerifyResult(False, errors, manifest)

        # consistency of the contents (only reached when every hash matched)
        try:
            witness = json.loads(z.read("witness.json"))["witness"]
            ids = {"ref": set(witness["ref_run_ids"]), "test": set(witness["test_run_ids"])}
            runs = {p: json.loads(z.read(p)) for p in listed if p.startswith("runs/")}
            for side in ("ref", "test"):
                got = {r["run_id"] for r in runs.values() if r["side"] == side}
                if got != ids[side] or len(got) != 3:
                    errors.append(f"runs/ does not contain exactly the three {side} runs named by the witness")
            if any(r["provenance"] != "FRESH_EXECUTION" for r in runs.values()):
                errors.append("a run in this bundle is not a fresh execution")
            if witness["witness_key"] != manifest["witness_key"]:
                errors.append("witness key in witness.json differs from the manifest")
            if manifest["bundle_id"] != "bdl_" + object_hash([f["sha256"] for f in manifest["files"]])[:24]:
                errors.append("bundle_id does not match the file list")
            for p in ("worlds/reference.world.json", "worlds/consumer.world.json"):
                if p not in listed:
                    errors.append(f"missing world description: {p}")
        except (ValueError, KeyError) as exc:
            errors.append(f"inconsistent bundle contents: {type(exc).__name__}: {exc}")
    return VerifyResult(not errors, errors, manifest)


def main(argv: list[str] | None = None) -> int:
    import sys
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m faultline.witnesses.bundle <bundle.zip>")
        return 2
    res = verify_bundle(args[0])
    if res.ok:
        m = res.manifest
        print(f"OK  {m['bundle_id']}  witness {m['witness_id']} ({m['witness_class']})  files: {len(m['files']) + 1}  mode: {m['mode']}")
        return 0
    for e in res.errors:
        print("ERROR:", e)
    print("bundle REJECTED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["BundleError", "BundleInfo", "VerifyResult", "write_bundle", "verify_bundle", "canonical_json"]
