"""Funnel statistics: discovered versus analysed, with exact counts and reasons. Never a compatibility score."""
import json
import sqlite3


def funnel(conn: sqlite3.Connection, analysis_id: str) -> dict:
    rels = conn.execute("SELECT * FROM relationship WHERE analysis_id=?", (analysis_id,)).fetchall()
    actionable = [r for r in rels if r["actionable"]]
    cells = conn.execute("SELECT * FROM cell WHERE analysis_id=?", (analysis_id,)).fetchall()
    consumers = conn.execute("SELECT cc.consumer_project_id, c.state FROM cell_consumer cc JOIN cell c ON c.id = cc.cell_id "
                             "WHERE c.analysis_id=?", (analysis_id,)).fetchall()
    stats = json.loads((conn.execute("SELECT stats_json FROM analysis WHERE id=?", (analysis_id,)).fetchone()["stats_json"]) or "{}")
    failed = stats.get("failed_consumers", [])
    return {
        "relationships_discovered": len(rels),
        "relationships_actionable": len(actionable),
        "suspected": sum(1 for r in rels if r["status"] == "SUSPECTED"),
        "consumers_discovered": len(actionable),
        "consumers_analysed": len({c["consumer_project_id"] for c in consumers}),
        "consumers_failed": failed,
        "cells": len(cells),
        "cells_by_state": {s: sum(1 for c in cells if c["state"] == s) for s in sorted({c["state"] for c in cells})},
    }
