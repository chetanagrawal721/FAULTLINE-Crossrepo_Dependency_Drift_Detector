"""M5.3: what happens to an analysis whose worker was cancelled, lost its lease or failed (no Docker needed)."""
import json

from faultline.analysis.lifecycle import mark_partial, reconcile_abandoned
from faultline.ingestion import service


def make_analysis(conn, status="ANALYZING", job_id=None):
    pid = service.create_project(conn, "p")
    aid = f"an_{status.lower()}_{job_id or 'x'}"
    conn.execute("INSERT INTO analysis(id, analysis_project_id, status, mode, options_json, started_at) VALUES (?,?,?, 'LIVE', ?, '2026-01-01T00:00:00Z')",
                 (aid, pid, status, json.dumps({"job_id": job_id} if job_id else {})))
    return aid


def stats(conn, aid):
    r = conn.execute("SELECT status, stats_json FROM analysis WHERE id=?", (aid,)).fetchone()
    return r["status"], json.loads(r["stats_json"] or "{}")


def test_a_cancelled_analysis_is_closed_labelled_and_never_left_in_progress(conn):
    aid = make_analysis(conn)
    assert mark_partial(conn, aid, "CANCELLED", "cancelled by the user") is True
    status, s = stats(conn, aid)
    assert status == "FAILED" and s["outcome"] == "CANCELLED" and s["partial"] is True and s["retained"] == {"cells": 0, "oracle_runs": 0, "findings": 0}


def test_a_finished_analysis_is_never_relabelled(conn):
    done = make_analysis(conn, "DONE")
    assert mark_partial(conn, done, "CANCELLED", "late cancel") is False
    assert stats(conn, done)[0] == "DONE"


def test_a_retried_job_closes_the_attempt_it_abandoned_and_only_that_one(conn):
    abandoned = make_analysis(conn, "ANALYZING", job_id="job_A")
    other_job = make_analysis(conn, "ANALYZING", job_id="job_B")
    finished = make_analysis(conn, "DONE", job_id="job_A")
    closed = reconcile_abandoned(conn, "job_A")
    assert closed == [abandoned]
    assert stats(conn, abandoned)[1]["outcome"] == "INTERRUPTED"
    assert stats(conn, other_job)[0] == "ANALYZING"                      # another job's running analysis is not touched
    assert stats(conn, finished)[0] == "DONE"
    assert reconcile_abandoned(conn, "job_A") == []                      # idempotent


def test_unfinished_oracle_jobs_of_a_closed_analysis_are_not_left_running(conn):
    aid = make_analysis(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO cell(id, analysis_id, artifact_project_id, ref_world_hash, test_world_hash, state) VALUES ('c1', ?, 'p', 'w1', 'w2', 'PENDING')", (aid,))
    conn.execute("INSERT INTO oracle_job(id, analysis_id, cell_id, oracle, oracle_version, world_hash, side, spec_json, cache_key, status, queued_at) "
                 "VALUES ('oj1', ?, 'c1', 'o_import', '1', 'w1', 'ref', '{}', 'k1', 'RUNNING', '2026-01-01T00:00:00Z')", (aid,))
    mark_partial(conn, aid, "INTERRUPTED", "lease lost")
    assert conn.execute("SELECT status FROM oracle_job WHERE id='oj1'").fetchone()[0] == "FAILED"
    assert stats(conn, aid)[1]["retained"]["cells"] == 1
