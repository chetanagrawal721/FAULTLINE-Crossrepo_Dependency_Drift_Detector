"""M5.4 TC-5.4.2: retention removes old data and never evidence that a retained finding refers to."""
import json
import os
import time

from faultline.storage.retention import cleanup, prune_logs, referenced
from faultline.storage.store import Store

OLD = time.time() - 40 * 86400
SHA = "a" * 40


def make(path, name, content=b"x"):
    p = path / name
    if name.endswith(".zip"):
        p.write_bytes(content)
    else:
        p.mkdir(parents=True)
        (p / "file.txt").write_bytes(content)
    os.utime(p, (OLD, OLD))
    return p


def seed(conn, store):
    """One finding with its evidence (snapshot, artifact, worlds, bundle) plus unrelated old data of every kind."""
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO analysis_project(id, name, mode, created_at) VALUES ('ap1','p','LIVE','2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO analysis(id, analysis_project_id, status, mode, options_json, started_at) VALUES ('an1','ap1','DONE','LIVE','{}','2026-01-01T00:00:00Z')")
    for pid, snap in (("prod", "snap_prod_key"), ("cons", "snap_cons_key"), ("other", "snap_other_key")):
        conn.execute("INSERT INTO snapshot(id, repository_id, sha, committed_at, store_path, ingest_status) VALUES (?, ?, ?, '2026-01-01T00:00:00Z', ?, 'OK')", (f"s_{pid}", f"r_{pid}", SHA, snap))
        conn.execute("INSERT INTO project(id, snapshot_id, rel_path, ecosystem, artifact_content_hash) VALUES (?,?, '.', 'pypi', ?)",
                     (pid, f"s_{pid}", "art_prod_hash" if pid == "prod" else ("art_other_hash" if pid == "other" else None)))
    conn.execute("INSERT INTO cell(id, analysis_id, artifact_project_id, ref_world_hash, test_world_hash, state) VALUES ('c1','an1','prod','w_ref_keep','w_test_keep','ANALYZED')")
    conn.execute("INSERT INTO cell_consumer(cell_id, consumer_project_id, relationship_id) VALUES ('c1','cons','rel1')")
    conn.execute("INSERT INTO finding(id, analysis_id, scope_kind, cell_id, verdict, headline, scope_json, priority, created_at) "
                 "VALUES ('f1','an1','ARTIFACT_CELL','c1','BREAK_WITNESSED','h', ?, 1, '2026-01-01T00:00:00Z')", (json.dumps({}),))
    conn.execute("INSERT INTO witness(id, analysis_id, cell_id, class, divergence, oracle, oracle_version, entry_point, witness_key, signature_json, ref_pass, test_fail, body_json) "
                 "VALUES ('wit_keep','an1','c1','BREAK','d','o_import','1','m','k1','{}',3,3,'{}')")
    for kind, keep, drop in (("snapshots", ["snap_prod_key", "snap_cons_key"], ["snap_other_key", "snap_orphan_key"]),
                             ("artifacts", ["art_prod_hash"], ["art_other_hash", "art_orphan_hash"]),
                             ("worlds", ["w_ref_keep", "w_test_keep"], ["w_orphan_one"])):
        for n in keep + drop:
            make(store.root / kind, n)
    (store.root / "bundles").mkdir(parents=True, exist_ok=True)
    make(store.root / "bundles", "wit_keep.zip")
    make(store.root / "bundles", "wit_gone.zip")


def test_what_a_finding_depends_on_is_identified(conn, tmp_path):
    store = Store(tmp_path / "store")
    seed(conn, store)
    keep = referenced(conn)
    assert keep["snapshots"] == {"snap_prod_key", "snap_cons_key"} and keep["artifacts"] == {"art_prod_hash"}
    assert keep["worlds"] == {"w_ref_keep", "w_test_keep"} and keep["bundles"] == {"wit_keep.zip"}


def test_tc_5_4_2_aggressive_cleanup_removes_unreferenced_data_and_keeps_every_referenced_item(conn, tmp_path):
    store = Store(tmp_path / "store")
    seed(conn, store)
    r = cleanup(conn, store, max_age_days=0)                                  # the most aggressive limit
    assert sorted(r.deleted["snapshots"]) == ["snap_orphan_key", "snap_other_key"]
    assert sorted(r.deleted["artifacts"]) == ["art_orphan_hash", "art_other_hash"] and r.deleted["worlds"] == ["w_orphan_one"] and r.deleted["bundles"] == ["wit_gone.zip"]
    for kind, name in (("snapshots", "snap_prod_key"), ("snapshots", "snap_cons_key"), ("artifacts", "art_prod_hash"), ("worlds", "w_ref_keep"),
                       ("worlds", "w_test_keep"), ("bundles", "wit_keep.zip")):
        assert (store.root / kind / name).exists(), (kind, name)                  # everything a retained finding refers to survived
    for kind, name in (("snapshots", "snap_orphan_key"), ("artifacts", "art_other_hash"), ("worlds", "w_orphan_one"), ("bundles", "wit_gone.zip")):
        assert not (store.root / kind / name).exists(), (kind, name)
    assert (store.root / "snapshots" / "snap_prod_key" / "file.txt").read_bytes() == b"x"                   # and its contents are intact
    again = cleanup(conn, store, max_age_days=0)                              # idempotent
    assert all(v == [] for v in again.deleted.values())


def test_recent_data_is_kept_and_a_dry_run_deletes_nothing(conn, tmp_path):
    store = Store(tmp_path / "store")
    seed(conn, store)
    fresh = store.root / "artifacts" / "art_fresh_hash"
    fresh.mkdir(parents=True)
    r = cleanup(conn, store, max_age_days=30)
    assert "art_fresh_hash" in r.kept_recent["artifacts"] and fresh.exists()
    assert "snap_other_key" in r.deleted["snapshots"] and not (store.root / "snapshots" / "snap_other_key").exists()      # 40 days old, over the 30 day limit
    store2 = Store(tmp_path / "store2")
    seed_dir = store2.root / "snapshots"
    make(seed_dir, "snap_zzz_key")
    d = cleanup(conn, store2, max_age_days=0, dry_run=True)
    assert d.deleted["snapshots"] == ["snap_zzz_key"] and (seed_dir / "snap_zzz_key").exists()


def test_the_wheelhouse_and_test_remotes_are_never_touched(conn, tmp_path):
    store = Store(tmp_path / "store")
    seed(conn, store)
    make(store.root / "remotes", "rm_keep_me")
    make(store.root, "wheels")
    cleanup(conn, store, max_age_days=0)
    assert (store.root / "remotes" / "rm_keep_me").exists() and (store.root / "wheels").exists()


def test_old_log_files_are_pruned_and_newer_ones_kept(tmp_path):
    old, new = tmp_path / "old.log", tmp_path / "new.log"
    old.write_text("x")
    new.write_text("y")
    os.utime(old, (OLD, OLD))
    assert prune_logs(tmp_path, max_age_days=30) == ["old.log"] and new.exists() and not old.exists()
