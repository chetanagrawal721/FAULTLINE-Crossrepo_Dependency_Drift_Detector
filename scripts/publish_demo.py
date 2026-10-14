"""Publish the demo repositories to GitHub (public), each as one commit on `main`.

    python scripts/publish_demo.py                      # dry run: builds the repositories locally and shows the plan
    python scripts/publish_demo.py --push               # creates/pushes chetanagrawal721/faultline-fixture-* with `gh`
    python scripts/publish_demo.py --push --owner NAME  # another account or organisation

The first pair (acme-models and notify-svc) was published earlier. This adds three more pairs so that each kind of finding can be shown live:
  call-site break      acme-http          + orders-svc            (urllib3 removed a keyword the library still passes)
  data-contract break  acme-contracts     + billing-svc-contract  (pydantic 2 rejects a payload pydantic 1 produced)
  silent divergence    acme-contracts     + billing-svc-union     (the text "42" is read as a number in one world and as text in the other)

Consumers name their dependencies by URL, so each published consumer's requirements.txt is rewritten to the published repository.
Nothing is created unless --push is given. A repository that already exists is left alone.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = ROOT / "fixtures" / "repos"
PREFIX = "faultline-fixture-"
GIT = ["git", "-c", "user.name=Faultline Fixtures", "-c", "user.email=fixtures@faultline.invalid", "-c", "core.autocrlf=false"]

# published name (without the prefix) -> (source tree, one-line description)
DEMO = {
    "acme-http": ("acme-http", "HTTP retry policies. Calls urllib3 Retry(method_whitelist=...), which urllib3 2 removed."),
    "orders-svc": ("orders-svc/C", "Consumer that resolves urllib3 2.x."),
    "acme-contracts": ("acme-contracts", "Pydantic wire models. Optional field without a default; Union[int, str]."),
    "billing-svc-contract": ("billing-svc/J", "Consumer on pydantic 2 that parses CustomerRequest payloads."),
    "billing-svc-union": ("billing-svc/E", "Consumer on pydantic 2 that parses Ref payloads."),
    "acme-showcase": ("acme-showcase", "One library with four modules: an import break, a call-site break, a data-contract break and a silent divergence."),
    "fulfilment-svc": ("fulfilment-svc", "Consumer on Werkzeug 3, urllib3 2 and pydantic 2 that uses all four modules."),
    "reporting-svc": ("reporting-svc", "Control consumer: resolves exactly the library's own dependencies."),
}
LOCAL_TO_PUBLISHED = {"acme-http": "acme-http", "acme-contracts": "acme-contracts", "acme-models": "acme-models", "acme-showcase": "acme-showcase"}


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed in {cwd}: {r.stderr.strip()}")
    return r.stdout.strip()


def rewrite_urls(text: str, owner: str) -> str:
    """git+https://github.com/faultline-demo/<repo>@scenario-X  ->  git+https://github.com/<owner>/faultline-fixture-<repo>@main"""
    def sub(m: re.Match) -> str:
        name = LOCAL_TO_PUBLISHED.get(m.group(1), m.group(1))
        return f"github.com/{owner}/{PREFIX}{name}@main"
    return re.sub(r"github\.com/faultline-demo/([\w.-]+)@scenario-\w+", sub, text)


def build(name: str, tree: str, desc: str, owner: str, dest: Path) -> Path:
    src = REPOS / tree
    repo = dest / (PREFIX + name)
    shutil.copytree(src, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in repo.rglob("requirements*.txt"):
        f.write_text(rewrite_urls(f.read_text(encoding="utf-8"), owner), encoding="utf-8", newline="\n")
    note = f"\n\n> Faultline demo fixture. {desc} Intentionally constructed to show one kind of finding; not a real library.\n"
    readme = repo / "README.md"
    readme.write_text((readme.read_text(encoding="utf-8").rstrip() if readme.exists() else f"# {PREFIX}{name}") + note, encoding="utf-8", newline="\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"Faultline demo fixture: {name}")
    return repo


def exists(slug: str) -> bool:
    return subprocess.run(["gh", "repo", "view", slug], capture_output=True, text=True).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--owner", default="chetanagrawal721")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="fl-demo-"))
    try:
        for name, (tree, desc) in DEMO.items():
            repo = build(name, tree, desc, a.owner, tmp)
            slug = f"{a.owner}/{PREFIX}{name}"
            sha = git(repo, "rev-parse", "HEAD")[:10]
            reqs = [f for f in repo.glob("requirements.txt")]
            urls = re.findall(r"github\.com/[\w.-]+/[\w.-]+@main", reqs[0].read_text(encoding="utf-8")) if reqs else []
            print(f"{slug}  commit {sha}" + (f"  depends on {', '.join(urls)}" if urls else ""))
            if not a.push:
                continue
            if exists(slug):
                print("   already exists: left alone")
                continue
            r = subprocess.run(["gh", "repo", "create", slug, "--public", "--description", f"Faultline demo fixture ({name}). {desc}"[:340],
                                "--source", str(repo), "--push"], capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"gh repo create {slug} failed: {r.stderr.strip()}")
            print("   published")
        print("\n" + ("published" if a.push else "DRY RUN: nothing was created. Use --push to publish."))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
