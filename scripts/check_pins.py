"""Fail on anything that is not pinned (TC-0.1.2).

Checks:
  * Python and uv versions in use equal versions.toml;
  * pyproject dependencies use exact == pins, and uv.lock exists;
  * frontend dependencies are exact versions (no ^, ~, *, latest) and package-lock.json exists;
  * every container image reference in Dockerfiles, compose files and versions.toml has @sha256:<64 hex>;
  * GitHub Actions use pinned versions (no @main / @master).

    python scripts/check_pins.py [--ci]     --ci also requires the running tools to match versions.toml
"""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
checked = {"python_deps": 0, "npm_deps": 0, "images": 0, "actions": 0}


def err(msg: str) -> None:
    errors.append(msg)


def check_tools(versions: dict) -> None:
    want_py = versions["python"]["version"]
    got_py = ".".join(map(str, sys.version_info[:3]))
    if got_py != want_py:
        err(f"python is {got_py}, versions.toml pins {want_py}")
    try:
        out = subprocess.check_output([sys.executable, "-m", "uv", "--version"], text=True, stderr=subprocess.STDOUT)
        got_uv = out.split()[1]
    except Exception:  # noqa: BLE001
        try:
            got_uv = subprocess.check_output(["uv", "--version"], text=True).split()[1]
        except Exception:  # noqa: BLE001
            got_uv = None
    if got_uv is None:
        err("uv is not available")
    elif got_uv != versions["tools"]["uv"]:
        err(f"uv is {got_uv}, versions.toml pins {versions['tools']['uv']}")


def check_python_deps() -> None:
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = list(py["project"]["dependencies"])
    for group in py.get("dependency-groups", {}).values():
        deps += [d for d in group if isinstance(d, str)]
    deps += py.get("build-system", {}).get("requires", [])
    for d in deps:
        checked["python_deps"] += 1
        if not re.search(r"==\s*[\w.]+", d):
            err(f"pyproject dependency is not exactly pinned: {d}")
    if not (ROOT / "uv.lock").exists():
        err("uv.lock is missing")
    rp = py["project"].get("requires-python", "")
    if "==" not in rp:
        err(f"requires-python should be an exact series (==3.12.*), got {rp!r}")


def check_npm_deps() -> None:
    pkg = ROOT / "frontend" / "package.json"
    if not pkg.exists():
        return
    data = json.loads(pkg.read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies"):
        for name, spec in data.get(section, {}).items():
            checked["npm_deps"] += 1
            if not re.fullmatch(r"\d+\.\d+\.\d+(-[\w.]+)?", spec):
                err(f"frontend/package.json {section}.{name} is not an exact version: {spec}")
    if not (ROOT / "frontend" / "package-lock.json").exists():
        err("frontend/package-lock.json is missing")


IMAGE_RE = re.compile(r"^\s*(?:FROM|image:)\s+(?:--platform=\S+\s+)?([^\s]+)", re.I | re.M)


def check_images(versions: dict) -> None:
    refs: list[tuple[str, str]] = []
    for f in list(ROOT.glob("docker/**/Dockerfile*")) + list(ROOT.glob("docker/**/*.yml")) + list(ROOT.glob("docker/**/*.yaml")):
        text = f.read_text(encoding="utf-8")
        stages = set(re.findall(r"^\s*FROM\s+\S+\s+AS\s+(\S+)", text, re.I | re.M))
        for m in IMAGE_RE.finditer(text):
            ref = m.group(1)
            if ref in stages or ref == "scratch":
                continue
            refs.append((str(f.relative_to(ROOT)), ref))
    for name, ref in versions.get("images", {}).items():
        refs.append((f"versions.toml[images].{name}", ref))
    for where, ref in refs:
        checked["images"] += 1
        if not re.search(r"@sha256:[0-9a-f]{64}$", ref):
            err(f"{where}: image {ref!r} has no @sha256 digest")


def check_actions() -> None:
    for f in (ROOT / ".github" / "workflows").glob("*.yml"):
        for m in re.finditer(r"uses:\s*([^\s#]+)", f.read_text(encoding="utf-8")):
            checked["actions"] += 1
            if re.search(r"@(main|master|latest)$", m.group(1)) or "@" not in m.group(1):
                err(f"{f.name}: action {m.group(1)} is not pinned")


def main() -> int:
    versions = tomllib.loads((ROOT / "versions.toml").read_text(encoding="utf-8"))
    check_tools(versions)
    check_python_deps()
    check_npm_deps()
    check_images(versions)
    check_actions()
    for e in errors:
        print("PIN ERROR:", e)
    print("checked:", ", ".join(f"{v} {k}" for k, v in checked.items()))
    if errors:
        return 1
    print("pins ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
