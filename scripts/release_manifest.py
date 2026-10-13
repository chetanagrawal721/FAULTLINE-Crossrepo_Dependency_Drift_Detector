"""Release manifest (M11.5): everything a release candidate was built from, so that it can be rebuilt from nothing and compared.

  python scripts/release_manifest.py [--out release/manifest.json]      write the manifest
  python scripts/release_manifest.py --check release/manifest.json      recompute and list every difference (exit 1 if any)

The manifest holds the commit, the pinned toolchain (versions.toml), the sandbox image reference and the hash of its build inputs, the
hashes of the lock files, of the backend and frontend sources, of the committed fixtures, of the OpenAPI document and of the evidence
bundle schema. It contains no timestamps, host names or paths, so two builds of the same commit give byte-identical manifests.
"""
import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.core.hashing import content_hash  # noqa: E402

SKIP_DIRS = {"__pycache__", "node_modules", "dist", ".venv", ".git", ".pytest_cache", ".ruff_cache"}
MANIFEST_VERSION = "1"


def tree_hash(root: Path, base: Path) -> dict:
    """{files, sha256} over the sorted (relative path, file hash) pairs below base; line endings are normalised so Windows and Linux agree."""
    entries = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and not p.is_symlink() and not (set(p.relative_to(root).parts) & SKIP_DIRS) and p.suffix != ".pyc":
            entries.append((p.relative_to(root).as_posix(), content_hash(p.read_bytes().replace(b"\r\n", b"\n"))))
    return {"files": len(entries), "sha256": content_hash(json.dumps(entries).encode())}


def file_hash(path: Path) -> str | None:
    return content_hash(path.read_bytes().replace(b"\r\n", b"\n")) if path.is_file() else None


def git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_manifest(root: Path = ROOT) -> dict:
    versions = tomllib.loads((root / "versions.toml").read_text(encoding="utf-8"))
    images = json.loads((root / "docker" / "images.lock.json").read_text(encoding="utf-8")) if (root / "docker" / "images.lock.json").is_file() else {}
    return {
        "manifest_version": MANIFEST_VERSION,
        "git": {"commit": git(root, "rev-parse", "HEAD")},
        "toolchain": versions,
        "images": {"lock": images, "build_inputs": tree_hash(root, root / "docker")},
        "locks": {"uv.lock": file_hash(root / "uv.lock"), "frontend/package-lock.json": file_hash(root / "frontend" / "package-lock.json"),
                  "pyproject.toml": file_hash(root / "pyproject.toml"), "versions.toml": file_hash(root / "versions.toml")},
        "sources": {"backend": tree_hash(root, root / "backend"), "frontend_src": tree_hash(root, root / "frontend" / "src"),
                    "tests": tree_hash(root, root / "tests"), "scripts": tree_hash(root, root / "scripts")},
        "data": {"fixtures": tree_hash(root, root / "fixtures"), "benchmark_cases": tree_hash(root, root / "benchmarks" / "cases"),
                 "conformance_matrix": file_hash(root / "docs" / "conformance" / "ps07-matrix.yaml")},
        "contracts": {"openapi": file_hash(root / "frontend" / "openapi.json"), "evidence_bundle_schema": file_hash(root / "docs" / "schemas" / "evidence-bundle-v1.json")},
        "release_blocking_suite": ["python tools/fl.py ci", "python scripts/conformance_report.py"],
    }


def flatten(d, prefix=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from flatten(v, f"{prefix}{k}.")
    else:
        yield prefix.rstrip("."), d


def differences(recorded: dict, current: dict) -> list[str]:
    a, b = dict(flatten(recorded)), dict(flatten(current))
    return [f"{k}: recorded {a.get(k)!r}, now {b.get(k)!r}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "release" / "manifest.json")
    ap.add_argument("--check", type=Path, help="compare the current tree with a recorded manifest")
    a = ap.parse_args()
    current = build_manifest()
    if a.check:
        diffs = differences(json.loads(a.check.read_text(encoding="utf-8")), current)
        for d in diffs:
            print("DIFFERENT", d)
        print("release manifest matches" if not diffs else f"{len(diffs)} difference(s)")
        return 1 if diffs else 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {a.out.relative_to(ROOT) if a.out.is_relative_to(ROOT) else a.out}  commit {current['git']['commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
