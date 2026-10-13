"""Heuristic detection of the worlds a producer's own CI would test (for the author-selected-matrix baseline).

HEURISTIC and labelled as such: it reads `.github/workflows/*.yml` for a Python version matrix and for `pip install` pins, and always
includes the artifact's own reference world. It does not run CI and cannot know what the author really tested.
"""
import re
from pathlib import Path


def producer_ci_worlds(repo_dir: Path) -> dict:
    wf = repo_dir / ".github" / "workflows"
    versions: set[str] = set()
    pins: set[str] = set()
    files = sorted(wf.glob("*.y*ml")) if wf.is_dir() else []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"python-version:\s*\[([^\]]+)\]", text):
            versions |= {v.strip().strip("'\"") for v in m.group(1).split(",")}
        for m in re.finditer(r"pip install[^\n]*?\b([A-Za-z0-9_.-]+==[0-9][\w.]*)", text):
            pins.add(m.group(1))
    return {"heuristic": True, "workflows": [f.name for f in files], "python_versions": sorted(versions), "pinned_installs": sorted(pins),
            "worlds_always_included": ["the artifact's own reference world"],
            "limitation": "derived from workflow text only; CI is not executed and unlisted worlds are unknown"}
