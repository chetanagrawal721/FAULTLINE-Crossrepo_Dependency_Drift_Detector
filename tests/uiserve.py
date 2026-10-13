"""Serves the real API (and the built UI) over an existing analysis database, so a real browser can read persisted records."""
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from faultline.api.main import create_app
from faultline.core.config import Settings
from faultline.core.enums import Mode


@contextmanager
def serve_database(conn, tmp_path: Path, mode: Mode = Mode.LIVE):
    db = conn.execute("PRAGMA database_list").fetchone()["file"]
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    settings = Settings(db_path=Path(db), store_path=tmp_path, mode=mode, admin_token=None, lease_seconds=30, heartbeat_seconds=10, poll_seconds=0.5)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        time.sleep(0.1)
        if server.started:
            break
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        t.join(timeout=10)
