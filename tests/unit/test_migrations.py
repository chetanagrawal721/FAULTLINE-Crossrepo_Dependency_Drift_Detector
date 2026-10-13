"""TC-0.2.1 to TC-0.2.4."""
import sqlite3

import pytest

from faultline.core.enums import JobStatus
from faultline.core.errors import FaultlineError, InvalidEnumError, InvalidTransitionError
from faultline.storage import jobs
from faultline.storage.db import connect
from faultline.storage.migrate import migrate, schema_version


def tables(c):
    return {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def schema_snapshot(c):
    return sorted((r["type"], r["name"], r["sql"]) for r in c.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))


def test_tc_0_2_1_migration_clean_and_idempotent(tmp_path):
    c = connect(tmp_path / "a.db")
    v1 = migrate(c)
    snap1 = schema_snapshot(c)
    assert v1 >= 2
    for expected in ("repository", "snapshot", "project", "manifest", "resolved_world", "cell", "oracle_run",
                     "witness", "finding", "job", "job_attempt", "schema_migrations"):
        assert expected in tables(c)
    assert migrate(c) == v1                      # second run is a no-op
    assert schema_snapshot(c) == snap1
    assert c.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == v1


def test_tc_0_2_2_failed_migration_rolls_back(tmp_path):
    d = tmp_path / "migs"
    d.mkdir()
    (d / "0001_ok.sql").write_text("CREATE TABLE a (id INTEGER PRIMARY KEY);\n")
    (d / "0002_bad.sql").write_text("CREATE TABLE b (id INTEGER PRIMARY KEY);\n"
                                    "INSERT INTO does_not_exist VALUES (1);\n")
    c = connect(tmp_path / "b.db")
    with pytest.raises(FaultlineError) as ei:
        migrate(c, d)
    assert ei.value.code.value == "MIGRATION_FAILED"
    assert "b" not in tables(c)                  # statements before the failure were rolled back
    assert "a" in tables(c) and schema_version(c) == 1      # earlier migration stays applied
    assert not c.in_transaction


def test_failed_first_migration_leaves_no_trace(tmp_path):
    d = tmp_path / "migs"
    d.mkdir()
    (d / "0001_bad.sql").write_text("CREATE TABLE x (id INTEGER);\nSELECT broken syntax here;\n")
    c = connect(tmp_path / "c.db")
    with pytest.raises(FaultlineError):
        migrate(c, d)
    assert tables(c) == set()


def test_modified_applied_migration_is_detected(tmp_path):
    d = tmp_path / "migs"
    d.mkdir()
    f = d / "0001_t.sql"
    f.write_text("CREATE TABLE t (id INTEGER);\n")
    c = connect(tmp_path / "d.db")
    migrate(c, d)
    f.write_text("CREATE TABLE t (id INTEGER, extra TEXT);\n")
    with pytest.raises(FaultlineError):
        migrate(c, d)


def test_tc_0_2_3_invalid_transition_rejected(conn):
    job, _ = jobs.create_job(conn, "noop")
    claimed = jobs.claim_next(conn, "w", 5)
    assert jobs.complete(conn, claimed.job.job_id, "w")
    assert jobs.get_job(conn, job.job_id).status == JobStatus.DONE
    with pytest.raises(InvalidTransitionError):
        jobs.set_status(conn, job.job_id, JobStatus.QUEUED)          # Python-level rule
    with pytest.raises(sqlite3.IntegrityError):                       # and the database-level rule
        conn.execute("UPDATE job SET status='QUEUED' WHERE job_id=?", (job.job_id,))
    assert jobs.get_job(conn, job.job_id).status == JobStatus.DONE   # nothing persisted


def test_tc_0_2_3_queued_cannot_jump_to_done(conn):
    job, _ = jobs.create_job(conn, "noop")
    with pytest.raises(InvalidTransitionError):
        jobs.set_status(conn, job.job_id, JobStatus.DONE)


def test_tc_0_2_3_unknown_enum_rejected(conn):
    job, _ = jobs.create_job(conn, "noop")
    with pytest.raises(InvalidEnumError):
        jobs.set_status(conn, job.job_id, "EXPLODED")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO analysis_project(id,name,mode,created_at) VALUES ('ap_1','x','WRONG','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO finding(id,analysis_id,scope_kind,verdict,headline,scope_json,priority,created_at) "
                     "VALUES ('f1','an_1','ARTIFACT_CELL','COMPATIBLE','h','{}',1,'t')")
    assert conn.execute("SELECT COUNT(*) FROM analysis_project").fetchone()[0] == 0


def _insert_chain(c):
    ts = "2026-10-13T00:00:00Z"
    c.execute("INSERT INTO analysis_project(id,name,mode,created_at) VALUES ('ap1','demo','FIXTURE',?)", (ts,))
    c.execute("INSERT INTO repository(id,analysis_project_id,owner,name) VALUES ('r1','ap1','o','n')")
    c.execute("INSERT INTO snapshot(id,repository_id,sha,committed_at,store_path,ingest_status) "
              "VALUES ('s1','r1',?,?,'p','OK')", ("a" * 40, ts))
    c.execute("INSERT INTO project(id,snapshot_id,rel_path,ecosystem) VALUES ('p1','s1','.','pypi')")
    c.execute("INSERT INTO manifest(id,project_id,path,kind,content_hash,parse_status) "
              "VALUES ('m1','p1','pyproject.toml','pyproject','h','OK')")
    c.execute("INSERT INTO env_profile(id,image_ref,arch,locale,tz,env_json,seed) VALUES ('ep1','img','amd64','C','UTC','{}',17)")
    for wh in ("w_ref", "w_test"):
        c.execute("INSERT INTO resolved_world(world_hash,ecosystem,runtime_json,env_profile_id,kind) "
                  "VALUES (?,?,?,?,?)", (wh, "pypi", "{}", "ep1", "reference" if wh == "w_ref" else "projected"))
    c.execute("INSERT INTO analysis(id,analysis_project_id,status,mode,options_json) VALUES ('an1','ap1','QUEUED','FIXTURE','{}')")
    c.execute("INSERT INTO cell(id,analysis_id,artifact_project_id,ref_world_hash,test_world_hash,state) "
              "VALUES ('c1','an1','p1','w_ref','w_test','PENDING')")
    c.execute("INSERT INTO oracle_job(id,analysis_id,cell_id,oracle,oracle_version,world_hash,side,spec_json,cache_key,status) "
              "VALUES ('oj1','an1','c1','o_import','1','w_ref','ref','{}','k1','DONE')")
    c.execute("INSERT INTO oracle_run(id,oracle_job_id,run_index,provenance,created_at,failure_class,result_json) "
              "VALUES ('or1','oj1',1,'FRESH_EXECUTION',?,'NONE','{}')", (ts,))
    c.execute("INSERT INTO witness(id,analysis_id,cell_id,class,divergence,oracle,oracle_version,entry_point,witness_key,"
              "signature_json,ref_pass,test_fail,body_json) VALUES ('wi1','an1','c1','BREAK','IMPORT_ERROR','o_import','1','m','wk','{}',3,3,'{}')")
    c.execute("INSERT INTO finding(id,analysis_id,scope_kind,cell_id,verdict,headline,scope_json,priority,created_at) "
              "VALUES ('f1','an1','ARTIFACT_CELL','c1','BREAK_WITNESSED','h','{}',1,?)", (ts,))


def test_tc_0_2_4_foreign_key_chain_and_protected_delete(conn):
    _insert_chain(conn)                                       # every insert succeeds
    assert conn.execute("SELECT COUNT(*) FROM finding").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM snapshot WHERE id='s1'")   # referenced through project -> cell -> finding
    with pytest.raises(sqlite3.IntegrityError):               # dangling reference refused
        conn.execute("INSERT INTO cell(id,analysis_id,artifact_project_id,ref_world_hash,test_world_hash,state) "
                     "VALUES ('c2','an1','nope','w_ref','w_test','PENDING')")
    assert conn.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0] == 1
