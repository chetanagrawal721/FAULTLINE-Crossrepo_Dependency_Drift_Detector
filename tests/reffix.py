"""Inserts artifact projects with a recorded (failed or partial) resolution, for reference-world policy tests."""
import itertools
import json

from faultline.ingestion.service import create_project

_n = itertools.count()


def _project(conn) -> str:
    i = next(_n)
    ap = create_project(conn, f"p{i}")
    conn.execute("INSERT INTO repository(id, analysis_project_id, owner, name, status) VALUES (?,?, 'o', 'r', 'INGESTED')", (f"repo_{i}", ap))
    conn.execute("INSERT INTO snapshot(id, repository_id, sha, committed_at, store_path, ingest_status) VALUES (?,?,?, '2024-10-30T00:00:00Z', 'k', 'OK')",
                 (f"snp_{i}", f"repo_{i}", f"{i:040d}"))
    conn.execute("INSERT INTO project(id, snapshot_id, rel_path, ecosystem) VALUES (?,?, '.', 'pypi')", (f"prj_{i}", f"snp_{i}"))
    return f"prj_{i}"


def failing_project(conn, reason: str) -> str:
    pid = _project(conn)
    conn.execute("INSERT INTO project_world(id, project_id, world_hash, source, resolver, resolver_args_json, resolved_at, status, failure_json) "
                 "VALUES (?,?, NULL, 'resolver', 'uv 0.13.0', '{}', '2024-10-30T00:00:00Z', 'FAILED', ?)",
                 (f"pw_{pid}", pid, json.dumps({"code": "RESOLUTION_FAILED", "reason": reason, "detail": "x"})))
    return pid


def partial_project(conn) -> str:
    pid = _project(conn)
    conn.execute("INSERT INTO env_profile(id, image_ref, arch, locale, tz, env_json, seed) VALUES ('ep_x','i','a','l','t','{}',0)")
    conn.execute("INSERT INTO resolved_world(world_hash, ecosystem, runtime_json, env_profile_id, kind) VALUES ('w_p','pypi','{}','ep_x','reference')")
    conn.execute("INSERT INTO project_world(id, project_id, world_hash, source, resolver, resolver_args_json, resolved_at, status) "
                 "VALUES (?,?, 'w_p', 'lockfile', 'uv_lock', '{}', '2024-10-30T00:00:00Z', 'OK_PARTIAL')", (f"pw_{pid}", pid))
    return pid
