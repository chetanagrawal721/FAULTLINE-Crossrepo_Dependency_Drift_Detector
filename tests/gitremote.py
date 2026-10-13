"""Builds local bare git repositories (including hostile ones) with git plumbing, for ingestion tests.

Plumbing (hash-object, mktree, commit-tree) accepts tree entries that normal `git add` refuses, such as a '..' path
component or a '.git' directory, which is exactly what a malicious repository can contain.
"""
import subprocess
from pathlib import Path

ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
       "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}


def git(repo: Path, *args: str, input_: bytes | None = None) -> str:
    import os
    r = subprocess.run(["git", "-C", str(repo), *args], input=input_, capture_output=True, env={**os.environ, **ENV})
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace')}")
    return r.stdout.decode().strip()


class Remote:
    """A bare repository. tree entries: {name: bytes | ("symlink", target) | ("gitlink", sha) | {nested dict}}."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "--bare", str(self.path)], check=True)
        git(self.path, "config", "uploadpack.allowAnySHA1InWant", "true")
        git(self.path, "config", "uploadpack.allowReachableSHA1InWant", "true")
        git(self.path, "config", "core.protectNTFS", "false")
        git(self.path, "config", "receive.fsckObjects", "false")

    def _tree(self, entries: dict) -> str:
        lines = []
        for name, v in sorted(entries.items()):
            if isinstance(v, dict):
                lines.append(f"040000 tree {self._tree(v)}\t{name}")
            elif isinstance(v, tuple) and v[0] == "symlink":
                lines.append(f"120000 blob {git(self.path, 'hash-object', '-w', '--stdin', input_=v[1].encode())}\t{name}")
            elif isinstance(v, tuple) and v[0] == "gitlink":
                lines.append(f"160000 commit {v[1]}\t{name}")
            else:
                lines.append(f"100644 blob {git(self.path, 'hash-object', '-w', '--stdin', input_=v)}\t{name}")
        return git(self.path, "mktree", input_=("\n".join(lines) + "\n").encode())

    def commit(self, entries: dict, branch: str = "main", tag: str | None = None, message: str = "c") -> str:
        tree = self._tree(entries)
        parent = []
        try:
            parent = ["-p", git(self.path, "rev-parse", f"refs/heads/{branch}")]
        except RuntimeError:
            pass
        sha = git(self.path, "commit-tree", tree, *parent, "-m", message)
        git(self.path, "update-ref", f"refs/heads/{branch}", sha)
        if tag:
            git(self.path, "update-ref", f"refs/tags/{tag}", sha)
        return sha

    def move_tag(self, tag: str, sha: str) -> None:
        git(self.path, "update-ref", f"refs/tags/{tag}", sha)
