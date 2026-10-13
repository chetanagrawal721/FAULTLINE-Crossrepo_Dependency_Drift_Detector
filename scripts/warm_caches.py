"""Warm everything the FIXTURE demo needs so it survives a GitHub, registry or network outage (milestone M12.2).

    python scripts/warm_caches.py

1. Builds a local git MIRROR of every committed fixture repository at its scenario state (under var/mirror/), so the demo can ingest
   them without GitHub: the same pinned commits, served from disk through the same sandboxed fetch.
2. Downloads and installs every fixture world (reference and consumer) so the wheelhouse volume and the offline world volumes are warm.
3. Verifies the result by listing which worlds are built.

Run it on the demo machine and on the backup machine while online. Nothing is fetched by branch or tag name at demo time.
"""
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from tests.gitremote import Remote  # noqa: E402
from tests.liveenv import nest  # noqa: E402
from tests.livefix import read_tree  # noqa: E402

from faultline.core.enums import WorldKind  # noqa: E402
from faultline.core.scenario import load_scenario  # noqa: E402
from faultline.resolvers.pinned import parse_pinned_lock  # noqa: E402
from faultline.sandbox import images  # noqa: E402
from faultline.sandbox.client import SandboxClient  # noqa: E402
from faultline.sandbox.sandboxd import Daemon, serve  # noqa: E402
from faultline.storage.store import Store  # noqa: E402
from faultline.worlds.builder import WorldBuilder  # noqa: E402

MIRROR = ROOT / "var" / "mirror"


def mirror_fixtures() -> list[dict]:
    out = []
    for p in sorted((ROOT / "fixtures" / "scenarios").glob("*.yaml")):
        sc = load_scenario(p)
        if not sc.evaluated or sc.kind == "real_world":
            continue
        trees = [(sc.artifact.repo, sc.artifact.path)] + [(c.repo, c.path) for c in sc.consumers] + [(b.repo, b.path) for b in sc.bystanders]
        for repo, path in trees:
            name = f"{sc.id}_{repo}".replace("-", "")
            sha = Remote(MIRROR / name).commit(nest(read_tree(ROOT / path)))
            out.append({"scenario": sc.id, "repo": repo, "mirror": f"var/mirror/{name}", "commit": sha})
    return out


def warm_worlds() -> list[dict]:
    store = Store(Path(tempfile.mkdtemp(prefix="fl-warm-")))
    d = Daemon("warm-token-not-secret", store=store)
    srv = serve("127.0.0.1", 0, d)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    sbx = SandboxClient(port=srv.server_address[1], token="warm-token-not-secret", timeout=900)
    image = images.default_image()
    builder = WorldBuilder(sbx, image)
    out, seen = [], set()
    for lock in sorted((ROOT / "fixtures" / "repos").rglob("requirements.lock.txt")):
        text = lock.read_text(encoding="utf-8")
        if text in seen:
            continue
        seen.add(text)
        w = builder.materialize(text, WorldKind.REFERENCE)
        res = builder.build(w, text)
        out.append({"lock": str(lock.relative_to(ROOT)), "packages": len(parse_pinned_lock(text)), "world": w.world_hash, "status": res.status})
        print(f"  {res.status:<7} {lock.relative_to(ROOT)}")
    return out


def main() -> int:
    print("mirroring fixture repositories ...")
    mirrors = mirror_fixtures()
    print(f"  {len(mirrors)} repository states mirrored under {MIRROR}")
    print("warming worlds ...")
    worlds = warm_worlds()
    bad = [w for w in worlds if w["status"] == "FAILED"]
    (ROOT / "var" / "warm-report.json").write_text(json.dumps({"mirrors": mirrors, "worlds": worlds}, indent=2), encoding="utf-8")
    print(f"done: {len(worlds)} worlds, {len(bad)} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
