"""Build the execution image and record its immutable id in docker/images.lock.json.

    python scripts/build_images.py

Jobs reference the image by its sha256 id, never by a mutable tag. The base image is pinned by digest in the
Dockerfile; scripts/check_pins.py enforces that.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "docker" / "images.lock.json"
IMAGES = {
    "exec-python": {"dockerfile": "docker/exec-python/Dockerfile", "tag": "faultline/exec-python:0.1.0"},
}


def main() -> int:
    lock = {}
    for name, spec in IMAGES.items():
        r = subprocess.run(["docker", "build", "-f", spec["dockerfile"], "-t", spec["tag"], "."], cwd=ROOT)
        if r.returncode:
            return r.returncode
        image_id = subprocess.check_output(["docker", "image", "inspect", spec["tag"], "--format", "{{.Id}}"],
                                           text=True).strip()
        base = [ln.split()[1] for ln in (ROOT / spec["dockerfile"]).read_text(encoding="utf-8").splitlines()
                if ln.startswith("FROM ")][0]
        lock[name] = {"tag": spec["tag"], "id": image_id, "base": base}
        print(f"{name}: {image_id}")
    LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
