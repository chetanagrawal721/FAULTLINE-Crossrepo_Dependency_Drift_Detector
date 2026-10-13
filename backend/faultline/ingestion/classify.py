"""Classification of snapshot files: which are manifests or lockfiles, which are ignored, which carry tags.

Pure functions over inventory entries (path and kind only). Nothing here reads file content or executes anything.
"""
import re
from dataclasses import dataclass

IGNORED_DIRS = {"node_modules", ".venv", "venv", "site-packages", "dist", "build", ".tox", "__pycache__", ".eggs",
                ".mypy_cache", ".pytest_cache", "bower_components", ".git"}
VENDOR_DIRS = {"vendor", "vendored", "third_party", "third-party", "thirdparty", "_vendor", "external"}

FIXED = {
    "pyproject.toml": "pyproject", "uv.lock": "uv_lock", "poetry.lock": "poetry_lock", "pipfile": "pipfile",
    "pipfile.lock": "pipfile_lock", "setup.py": "setup_py", "setup.cfg": "setup_cfg", "package.json": "package_json",
    "package-lock.json": "package_lock", "npm-shrinkwrap.json": "package_lock", "pnpm-lock.yaml": "pnpm_lock",
    "yarn.lock": "yarn_lock", "pom.xml": "pom", "build.gradle": "gradle", "build.gradle.kts": "gradle",
}
REQ = re.compile(r"^requirements[\w.-]*\.(txt|in)$", re.I)
CONSTRAINTS = re.compile(r"^constraints[\w.-]*\.txt$", re.I)

# manifest kinds Faultline can read, by ecosystem; the rest are recorded as present but unsupported
SUPPORTED = {"requirements", "constraints", "pyproject", "uv_lock", "poetry_lock", "package_json", "package_lock", "pom"}
ECOSYSTEM = {"requirements": "pypi", "constraints": "pypi", "pyproject": "pypi", "uv_lock": "pypi", "poetry_lock": "pypi",
             "pipfile": "pypi", "pipfile_lock": "pypi", "setup_py": "pypi", "setup_cfg": "pypi",
             "package_json": "npm", "package_lock": "npm", "pnpm_lock": "npm", "yarn_lock": "npm", "pom": "maven",
             "gradle": "maven"}


@dataclass(frozen=True)
class Classified:
    role: str                  # manifest | ignored | source | other
    manifest_kind: str | None
    tags: tuple[str, ...]


def manifest_kind(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    low = name.lower()
    if low in FIXED:
        return FIXED[low]
    if CONSTRAINTS.match(name):
        return "constraints"
    if REQ.match(name):
        return "requirements"
    parent = path.rsplit("/", 2)[-2].lower() if path.count("/") >= 1 else ""
    if parent in ("requirements", "reqs") and re.match(r"^[\w.-]+\.(txt|in)$", name, re.I):
        return "constraints" if CONSTRAINTS.match(name) else "requirements"          # requirements/base.txt, requirements/dev.txt
    return None


def classify(path: str, kind: str = "file") -> Classified:
    parts = path.split("/")
    dirs = [p.lower() for p in parts[:-1]]
    name = parts[-1]
    tags: list[str] = []
    if any(d in IGNORED_DIRS for d in dirs):
        return Classified("ignored", None, ("IGNORED",))
    if any(d in VENDOR_DIRS for d in dirs):
        tags.append("VENDORED")
    if name.endswith(("_pb2.py", "_pb2_grpc.py", ".pb.go", "_pb.js")) or ".generated." in name:
        tags.append("GENERATED")
    if name.endswith(".ipynb"):
        tags.append("NOTEBOOK")
    if any(d in ("test", "tests", "__tests__", "spec") for d in dirs) or name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.ts")):
        tags.append("TEST")
    mk = manifest_kind(path) if kind in ("file", "lfs_pointer") else None
    if mk and "VENDORED" not in tags:
        return Classified("manifest", mk, tuple(tags))
    if name.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".proto", ".ipynb")):
        return Classified("source", None, tuple(tags))
    return Classified("other", None, tuple(tags))
