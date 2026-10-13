"""Shared real-Docker environment for oracle tests: worlds are built once per module and reused."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from faultline.core.enums import WorldKind
from faultline.oracles.artifacts import prepare_artifact
from faultline.sandbox.client import SandboxClient
from faultline.storage.db import connect
from faultline.storage.migrate import migrate
from faultline.worlds.builder import WorldBuilder
from faultline.worlds.overlay import overlay_lock

ROOT = Path(__file__).resolve().parents[2]
REPOS = ROOT / "fixtures" / "repos"
LOCKS = {"ref": REPOS / "acme-models" / "requirements.lock.txt",
         "notify_d": REPOS / "notify-svc" / "D" / "requirements.lock.txt",
         "billing_h": REPOS / "billing-svc" / "H" / "requirements.lock.txt"}
TEST_LOCK = REPOS / "acme-models" / "requirements.test.lock.txt"


@pytest.fixture(scope="module")
def env(daemon, image, tmp_path_factory):
    """Runtime worlds (ref, scenario D consumer, scenario H consumer), their test overlays, and the artifact."""
    db = connect(tmp_path_factory.mktemp("db") / "w.db")
    migrate(db)
    sbx = SandboxClient(port=daemon.port, token="test-token-not-secret", timeout=600)
    builder = WorldBuilder(sbx, image, db)
    worlds, overlays, locks = {}, {}, {}
    test_text = TEST_LOCK.read_text(encoding="utf-8")
    for name, path in LOCKS.items():
        text = path.read_text(encoding="utf-8")
        locks[name] = text
        w = builder.materialize(text, WorldKind.REFERENCE if name == "ref" else WorldKind.PROJECTED)
        res = builder.build(w, text)
        assert res.status in ("BUILT", "REUSED"), res.reason
        worlds[name] = w
        ov = overlay_lock(text, test_text)
        ow = builder.materialize(ov.lock_text, WorldKind.OVERLAY, scopes=ov.scopes())
        res = builder.build(ow, ov.lock_text)
        assert res.status in ("BUILT", "REUSED"), res.reason
        worlds[name + "+tests"] = ow
        overlays[name] = ov
    artifact = prepare_artifact(REPOS / "acme-models", daemon.store)
    return SimpleNamespace(sbx=sbx, image=image, worlds=worlds, overlays=overlays, locks=locks, artifact=artifact,
                           builder=builder, conn=db)
