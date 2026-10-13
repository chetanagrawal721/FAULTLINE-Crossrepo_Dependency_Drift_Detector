"""Generate the fixture repositories and their resolved lock files (milestone M1.1).

    python scripts/make_fixtures.py            # (re)writes fixtures/repos/** and runs `uv pip compile`

Layout (pushed to GitHub later as repos with one tag per scenario, see scripts/push_fixtures.sh):
    fixtures/repos/acme-models/           the shared artifact (same tree for every scenario)
    fixtures/repos/<consumer>/<SCENARIO>/ one tree per scenario tag

Lock files are produced with `uv pip compile --generate-hashes --python-platform linux --python-version 3.12
--exclude-newer 2024-10-30`, so they are reproducible and Werkzeug resolves to 3.0.6 (3.1.0 came out on 2024-10-31).
Facts the scenarios depend on were verified by scripts/verify_fixture_facts.py (milestone M1.0).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = ROOT / "fixtures" / "repos"
CUTOFF = "2024-10-30T00:00:00Z"
GIT_DEP = "acme-models[web] @ git+https://github.com/faultline-demo/acme-models@scenario-{sc}"

FILES: dict[str, str] = {}


def put(rel: str, text: str) -> None:
    FILES[rel] = text.lstrip("\n")


# ----------------------------------------------------------------------------- shared artifact
put("acme-models/pyproject.toml", '''
[project]
name = "acme-models"
version = "1.3.0"
description = "Shared customer models used by orders, billing and notify services (Faultline fixture)"
requires-python = ">=3.9"
dependencies = ["pydantic>=1.10"]

[project.optional-dependencies]
web = ["flask>=2.2"]

[dependency-groups]
test = ["pytest>=7"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_models"]
''')
put("acme-models/src/acme_models/__init__.py", '''
"""Shared models. Only pure-Python code, so it can be mounted without a build step."""
__version__ = "1.3.0"
''')
put("acme-models/src/acme_models/customer.py", '''
from pydantic import BaseModel


class CustomerRequest(BaseModel):
    customer_id: int
    email: str
    loyalty_points: int = 0


def to_payload(request: CustomerRequest) -> dict:
    """Serialise for the wire. `.dict()` exists in pydantic 1 and (deprecated) in pydantic 2."""
    return request.dict()
''')
put("acme-models/src/acme_models/web.py", '''
"""HTTP helpers. Needs the `web` extra (Flask); consumers that do not use it never import this module."""
from flask import Flask, jsonify

from .customer import CustomerRequest, to_payload


def make_app() -> Flask:
    app = Flask(__name__)

    @app.get("/customers/<int:customer_id>")
    def show(customer_id: int):
        req = CustomerRequest(customer_id=customer_id, email=f"user{customer_id}@example.com")
        return jsonify(to_payload(req))

    return app
''')
put("acme-models/tests/test_customer.py", '''
from acme_models.customer import CustomerRequest, to_payload


def test_round_trip():
    req = CustomerRequest(customer_id=7, email="a@example.com")
    assert to_payload(req) == {"customer_id": 7, "email": "a@example.com", "loyalty_points": 0}


def test_default_points():
    assert CustomerRequest(customer_id=1, email="b@example.com").loyalty_points == 0
''')
put("acme-models/tests/test_web.py", '''
import importlib.util

import pytest

# The web extra is optional. A world WITHOUT Flask skips these tests; a world where Flask is present but broken must
# run them and fail (importorskip would hide that by skipping on ImportError).
pytestmark = pytest.mark.skipif(importlib.util.find_spec("flask") is None, reason="web extra not installed")


def test_show_customer():
    from acme_models.web import make_app

    client = make_app().test_client()
    body = client.get("/customers/3").get_json()
    assert body["customer_id"] == 3 and body["loyalty_points"] == 0
''')
put("acme-models/requirements.in", """
# Reference world (what the artifact's own CI resolves). Exact pins match the verified facts in M1.0.
pydantic==1.10.13
flask==2.2.2
werkzeug==2.2.3
""")
put("acme-models/requirements.test.in", """
# Test-only packages, overlaid on whichever runtime world is under test (PC-5).
pytest==8.3.3
""")
put("acme-models/README.md", """
# acme-models (Faultline fixture)

Shared artifact for the Faultline demo scenarios. `requirements.lock.txt` is the reference world;
`requirements.test.lock.txt` holds test-only packages. Regenerate with `python scripts/make_fixtures.py`.
""")

# ----------------------------------------------------------------------------- consumers
CONSUMERS = {
    # name/scenario: (requirements.txt content for the lock, imports of the artifact)
    "orders-svc/A": ("pydantic==1.10.13\nflask==2.2.2\nwerkzeug==2.2.3\n", "acme_models.customer"),
    "orders-svc/D": ("pydantic==1.10.13\nflask==2.2.2\nwerkzeug==2.2.3\n", "acme_models.customer"),
    # D: Flask is pinned, Werkzeug is not, and click/itsdangerous are older pins (irrelevant noise for attribution)
    "notify-svc/D": ("pydantic==1.10.13\nflask==2.2.2\nclick==8.1.7\nitsdangerous==2.1.2\n", "acme_models.web"),
    # H: a newer pydantic; this service never imports the web module
    "billing-svc/H": ("pydantic==2.7.4\n", "acme_models.customer"),
}
for key, (reqs, mod) in CONSUMERS.items():
    name, sc = key.split("/")
    put(f"{key}/requirements.txt", reqs + GIT_DEP.format(sc=sc) + "\n")
    put(f"{key}/requirements.in", reqs)
    put(f"{key}/app/main.py", f'''
"""{name} (Faultline fixture, scenario {sc}). Uses the shared artifact."""
import {mod} as shared

print("loaded", shared.__name__)
''')
    put(f"{key}/README.md", f"# {name} (Faultline fixture, scenario {sc})\n\n`requirements.lock.txt` is the resolved world.\n")


def compile_lock(src: Path, out: Path, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, "-m", "uv", "pip", "compile", str(src), "--generate-hashes", "--no-header",
           "--python-version", "3.12", "--python-platform", "x86_64-unknown-linux-gnu",
           "--exclude-newer", CUTOFF, "--only-binary", ":all:", "--no-annotate", "-q", "-o", str(out),
           *(extra or [])]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"uv compile failed for {src}:\n{r.stderr}")
    banner = (f"# Resolved by: uv pip compile --generate-hashes --python-version 3.12 --python-platform "
              f"x86_64-unknown-linux-gnu --exclude-newer {CUTOFF} --only-binary :all:\n# Source: {src.name}\n")
    out.write_text(banner + out.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> int:
    for rel, text in FILES.items():
        p = REPOS / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    art = REPOS / "acme-models"
    compile_lock(art / "requirements.in", art / "requirements.lock.txt")
    compile_lock(art / "requirements.test.in", art / "requirements.test.lock.txt")
    for key in CONSUMERS:
        d = REPOS / key
        compile_lock(d / "requirements.in", d / "requirements.lock.txt")
    # the .in files are inputs for locking only; keep them next to the locks for reproducibility
    print(f"wrote {len(FILES)} files and {2 + len(CONSUMERS)} lock files under {REPOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
