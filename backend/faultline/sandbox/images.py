"""Image allowlist. Jobs name an image by its immutable sha256 id; anything not in docker/images.lock.json is refused."""
import json
import re
from pathlib import Path

from ..core.config import repo_root

IMAGE_REF = re.compile(r"^(sha256:[0-9a-f]{64}|[\w./:-]+@sha256:[0-9a-f]{64})$")


def lock_path() -> Path:
    return repo_root() / "docker" / "images.lock.json"


def load_lock(path: Path | None = None) -> dict:
    p = path or lock_path()
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def allowed_ids(path: Path | None = None) -> dict[str, str]:
    """{image id: logical name}"""
    return {v["id"]: k for k, v in load_lock(path).items()}


def require_allowed(image: str, path: Path | None = None) -> str:
    if not IMAGE_REF.match(image):
        raise ValueError(f"image reference must be an immutable sha256 id or name@sha256:digest, got {image!r}")
    if image not in allowed_ids(path):
        raise ValueError("image is not in the allowlist (docker/images.lock.json); build it with scripts/build_images.py")
    return image


def default_image(name: str = "exec-python", path: Path | None = None) -> str:
    lock = load_lock(path)
    if name not in lock:
        raise ValueError(f"image {name!r} is not built: run scripts/build_images.py")
    return lock[name]["id"]
