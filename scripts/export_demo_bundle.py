"""Run the full fixture pipeline for scenario D once (real Docker) and export the resulting evidence bundle.

    python scripts/export_demo_bundle.py [OUT.zip]

It builds the reference and consumer worlds offline, verifies the O-import witness with 3 + 3 fresh runs, stores it
in a throwaway database, and writes the bundle. Needs Docker and the built image (python scripts/build_images.py).
"""
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.analysis.fixture import ensure_fixture_cell  # noqa: E402
from faultline.core.enums import WorldKind  # noqa: E402
from faultline.oracles.artifacts import prepare_artifact  # noqa: E402
from faultline.oracles.o_import import ORACLE, ORACLE_VERSION, plan_modules, run_o_import  # noqa: E402
from faultline.sandbox import images  # noqa: E402
from faultline.sandbox.client import SandboxClient  # noqa: E402
from faultline.sandbox.sandboxd import Daemon, serve  # noqa: E402
from faultline.storage.db import connect  # noqa: E402
from faultline.storage.migrate import migrate  # noqa: E402
from faultline.storage.store import Store  # noqa: E402
from faultline.witnesses.bundle import write_bundle  # noqa: E402
from faultline.witnesses.verify import verify_cell  # noqa: E402
from faultline.worlds.builder import WorldBuilder  # noqa: E402

REPOS = ROOT / "fixtures" / "repos"


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "var" / "witness-D.bundle.zip"
    daemon = Daemon("local", store=Store(Path(tempfile.mkdtemp(prefix="fl-store-"))))
    srv = serve("127.0.0.1", 0, daemon)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sbx = SandboxClient(port=srv.server_address[1], token="local", timeout=600)
    image = images.default_image()
    db = connect(Path(tempfile.mkdtemp(prefix="fl-db-")) / "demo.db")
    migrate(db)
    builder = WorldBuilder(sbx, image, db)

    def world(lock: Path, kind: WorldKind):
        text = lock.read_text(encoding="utf-8")
        w = builder.materialize(text, kind)
        res = builder.build(w, text)
        print(f"world {w.world_hash} {res.status}", flush=True)
        return w

    ref = world(REPOS / "acme-models" / "requirements.lock.txt", WorldKind.REFERENCE)
    test = world(REPOS / "notify-svc" / "D" / "requirements.lock.txt", WorldKind.PROJECTED)
    artifact = prepare_artifact(REPOS / "acme-models", daemon.store)
    cell = ensure_fixture_cell(db, scenario_id="D", consumer="notify-svc", artifact_hash=artifact,
                               ref_world=ref, test_world=test, env=builder.env)
    modules = plan_modules("acme_models", ["acme_models.web"])

    def run(world_hash: str):
        return run_o_import(sbx, image, world_hash=world_hash, artifact_hash=artifact, top_level="acme_models",
                            modules=modules)

    v = verify_cell(db, cell, oracle=ORACLE, version=ORACLE_VERSION, run_in_world=run, args={"modules": modules})
    for d in v.decisions:
        print(f"{d.entry:18} {d.decision.value:14} {d.reason}")
    wid = v.decision_for("acme_models.web").witness_id
    if not wid:
        print("no witness was produced")
        return 1
    info = write_bundle(db, wid, out, daemon.store, mode="FIXTURE")
    print(f"bundle {info.path} {info.bundle_id} sha256={info.sha256} {info.size} bytes {info.files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
