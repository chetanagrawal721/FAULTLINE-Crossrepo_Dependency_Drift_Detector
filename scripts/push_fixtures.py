"""Turn fixtures/repos into git repositories with one tag per scenario, and optionally push them to GitHub.

    python scripts/push_fixtures.py                       # build local repos in a temp dir and show the plan (default)
    python scripts/push_fixtures.py --out DIR             # keep the local repos in DIR
    python scripts/push_fixtures.py --push --org NAME     # create/push NAME/<repo> with gh (needs `gh auth login`)

Nothing is pushed unless --push is given. Tags are scenario-<ID>. A repo that has one tree per scenario
(fixtures/repos/<repo>/<ID>/) gets one commit per scenario; a repo with a single tree (acme-models) gets one
commit tagged with every scenario.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = ROOT / "fixtures" / "repos"
GIT = ["git", "-c", "user.name=Faultline Fixtures", "-c", "user.email=fixtures@faultline.invalid", "-c", "core.autocrlf=false"]


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed in {cwd}: {r.stderr}")
    return r.stdout.strip()


def scenarios_of(repo: Path) -> list[str]:
    """Scenario ids that have their own subtree, or [] for a single-tree repo."""
    return sorted(p.name for p in repo.iterdir() if p.is_dir() and len(p.name) == 1 and p.name.isupper())


def all_scenarios() -> list[str]:
    return sorted(p.stem for p in (ROOT / "fixtures" / "scenarios").glob("*.yaml"))


def build(repo_dir: Path, dest: Path) -> dict[str, str]:
    """Create dest as a git repo. Returns {tag: commit sha}."""
    dest.mkdir(parents=True)
    git(dest, "init", "-q", "-b", "main")
    tags: dict[str, str] = {}
    subtrees = scenarios_of(repo_dir)

    def snapshot(src: Path) -> None:
        for item in dest.iterdir():
            if item.name != ".git":
                shutil.rmtree(item) if item.is_dir() else item.unlink()
        for f in src.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                t = dest / f.relative_to(src)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, t)

    if subtrees:
        for sc in subtrees:
            snapshot(repo_dir / sc)
            git(dest, "add", "-A")
            git(dest, "commit", "-q", "--allow-empty", "-m", f"scenario {sc}")
            git(dest, "tag", f"scenario-{sc}")
            tags[f"scenario-{sc}"] = git(dest, "rev-parse", "HEAD")
    else:
        snapshot(repo_dir)
        git(dest, "add", "-A")
        git(dest, "commit", "-q", "-m", "shared artifact")
        sha = git(dest, "rev-parse", "HEAD")
        for sc in all_scenarios():
            git(dest, "tag", f"scenario-{sc}")
            tags[f"scenario-{sc}"] = sha
    return tags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--org", default="faultline-demo")
    a = ap.parse_args()
    out = a.out or Path(tempfile.mkdtemp(prefix="fl-fixture-repos-"))
    out.mkdir(parents=True, exist_ok=True)
    plan = {}
    for repo_dir in sorted(p for p in REPOS.iterdir() if p.is_dir()):
        dest = out / repo_dir.name
        if dest.exists():
            shutil.rmtree(dest)
        plan[repo_dir.name] = build(repo_dir, dest)
    for name, tags in plan.items():
        print(f"{a.org}/{name}: " + ", ".join(f"{t}@{s[:8]}" for t, s in tags.items()))
    if not a.push:
        print(f"\nlocal repositories in {out}\nDRY RUN: nothing was pushed. Use --push --org <name> to publish.")
        return 0
    for name in plan:
        dest = out / name
        subprocess.run(["gh", "repo", "create", f"{a.org}/{name}", "--public", "--source", str(dest), "--remote", "origin"],
                       check=False)
        git(dest, "push", "origin", "main", "--tags")
        print(f"pushed {a.org}/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
