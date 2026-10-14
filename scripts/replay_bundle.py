"""Replay a witness from its evidence bundle on THIS machine, with a private sandbox daemon and an empty store.

    python scripts/replay_bundle.py evidence/bundles/scenario-D-witness.zip [--log replay.log]

This is the check behind "reproduces on another machine": the bundle is verified first, the artifact comes from the bundle, the wheels are
fetched only by hash from the bundle's lock files, and the outcome is EXACT_REPRODUCTION, ENVIRONMENT_LIMITED or NON_REPRODUCIBLE with reasons.
Run it on a clean machine (CI runs it on a fresh runner). Needs Docker and the built sandbox image (python scripts/build_images.py).
Exit status is 0 unless the outcome is NON_REPRODUCIBLE or the bundle is refused.
"""
import argparse
import platform
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.sandbox import images  # noqa: E402
from faultline.sandbox.client import SandboxClient  # noqa: E402
from faultline.sandbox.sandboxd import Daemon, serve  # noqa: E402
from faultline.storage.store import Store  # noqa: E402
from faultline.witnesses.replay import ReplayOutcome, ReplayRefused, replay  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--log", type=Path, default=None)
    a = ap.parse_args()
    lines = [f"machine: {platform.system()} {platform.release()} ({platform.machine()}), python {platform.python_version()}",
             f"bundle: {a.bundle.name}, {a.bundle.stat().st_size} bytes", f"started: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"]
    store = Store(Path(tempfile.mkdtemp(prefix="fl-replay-")))              # empty: nothing is cached from any earlier run
    token = "replay-token-not-secret"
    srv = serve("127.0.0.1", 0, Daemon(token, store=store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sbx = SandboxClient(port=srv.server_address[1], token=token, timeout=1200)
    code = 0
    try:
        res = replay(a.bundle, sbx, images.default_image(), store)
        lines.append(f"outcome: {res.outcome.value}")
        lines += [f"  - {r}" for r in res.reasons]
        code = 1 if res.outcome == ReplayOutcome.NON_REPRODUCIBLE else 0
    except ReplayRefused as e:
        lines.append("outcome: REFUSED (the bundle failed verification, nothing was executed)")
        lines += [f"  - {x}" for x in e.errors]
        code = 1
    finally:
        srv.shutdown()
    lines.append(f"finished: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    text = "\n".join(lines)
    print(text)
    if a.log:
        a.log.parent.mkdir(parents=True, exist_ok=True)
        a.log.write_text(text + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
