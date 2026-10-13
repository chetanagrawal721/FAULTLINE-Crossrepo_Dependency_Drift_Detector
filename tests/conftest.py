import os
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

from faultline.api.main import create_app
from faultline.core.config import Settings
from faultline.core.enums import Mode
from faultline.sandbox import images, runner, status
from faultline.sandbox.client import SandboxClient
from faultline.sandbox.sandboxd import Daemon, serve
from faultline.storage.db import connect
from faultline.storage.migrate import migrate
from faultline.storage.store import Store

TOKEN = "test-token-not-secret"


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "t.db", store_path=tmp_path / "store", mode=Mode.FIXTURE,
                    admin_token=None, lease_seconds=1.5, heartbeat_seconds=0.3, poll_seconds=0.05)


@pytest.fixture
def conn(settings):
    c = connect(settings.db_path)
    migrate(c)
    yield c
    c.close()


@pytest.fixture
def client(settings, monkeypatch):
    from faultline.sandbox import status
    from faultline.sandbox.client import SandboxClient
    status._cache.update(at=0.0, value=None)
    # point the API at a port nothing listens on: tests must not depend on a developer's running sandboxd
    monkeypatch.setattr(status, "SandboxClient", lambda: SandboxClient(port=1, token="x", timeout=1))
    with TestClient(create_app(settings)) as c:
        yield c

def docker_available() -> bool:
    return runner.docker_ok()


def labelled_containers() -> list[str]:
    r = subprocess.run(["docker", "ps", "-a", "--filter", "label=faultline=1", "--format", "{{.Names}}"],
                       capture_output=True, text=True, timeout=30)
    return [n for n in r.stdout.split() if n and n != "faultline-egress"]      # job containers only: the egress proxy is long-lived by design


@pytest.fixture(scope="session")
def image():
    if not docker_available():
        pytest.skip("Docker is not running")
    try:
        return images.default_image()
    except ValueError:
        pytest.skip("execution image not built: python scripts/build_images.py")


@pytest.fixture(scope="session")
def daemon(tmp_path_factory, image):
    """A real sandboxd (real Docker) on an ephemeral loopback port, in this process."""
    os.environ["FAULTLINE_SECRET_CANARY"] = "canary-must-never-reach-a-container"
    runner.sweep_orphans()
    d = Daemon(TOKEN, store=Store(tmp_path_factory.mktemp("store")))
    srv = serve("127.0.0.1", 0, d)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    d.port = srv.server_address[1]
    yield d
    srv.shutdown()
    runner.sweep_orphans()


@pytest.fixture
def sbx(daemon):
    status._cache.update(at=0.0, value=None)
    return SandboxClient(port=daemon.port, token=TOKEN, timeout=120)


@pytest.fixture
def probe(sbx, image):
    def run(name, args=None, **limits):
        job = {"image": image, "probe": name, "args": args or {}}
        if limits:
            job["limits"] = limits
        return sbx.submit(job)
    return run
