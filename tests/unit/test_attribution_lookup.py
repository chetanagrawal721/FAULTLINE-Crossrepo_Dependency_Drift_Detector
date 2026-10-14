"""A repeated analysis reuses the earlier witness. Its attribution must still be shown for the new cell, through the new finding."""
import sqlite3

from faultline.analysis.read import _attribution
from faultline.storage.migrate import migrate


def test_a_repeated_analysis_shows_the_attribution_of_the_reused_witness(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO witness(id, analysis_id, cell_id, class, divergence, oracle, oracle_version, entry_point, witness_key, signature_json, ref_pass, test_fail, body_json) "
                 "VALUES ('wit_1','an_old','cell_old','BREAK','IMPORT_ERROR','o_import','1','m','wk','{}',3,3,'{}')")
    conn.execute("INSERT INTO attribution(id, witness_id, status, minimal_set_json, sidedness, forced_worlds_used, runs, notes_json) VALUES ('att_1','wit_1','COMPLETE','[\"werkzeug\"]','two_sided',1,4,'{}')")
    for fid, cell in (("fnd_old", "cell_old"), ("fnd_new", "cell_new")):
        conn.execute("INSERT INTO finding(id, analysis_id, scope_kind, cell_id, verdict, headline, scope_json, priority, created_at) VALUES (?,?,'ARTIFACT_CELL',?,'BREAK_WITNESSED','h','{}',1,'now')", (fid, "an_" + cell, cell))
        conn.execute("INSERT INTO finding_evidence(finding_id, evidence_kind, evidence_id) VALUES (?, 'WITNESS', 'wit_1')", (fid,))
    assert _attribution(conn, "cell_old").minimal == ["werkzeug"]
    new = _attribution(conn, "cell_new")                                                      # the second analysis: another cell, the same witness
    assert new is not None and new.minimal == ["werkzeug"] and new.status == "COMPLETE"
    assert _attribution(conn, "cell_none") is None
