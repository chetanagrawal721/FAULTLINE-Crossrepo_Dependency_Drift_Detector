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
put("acme-models/src/acme_models/settings.py", '''
"""Scenario B: uses the pydantic 1 location of BaseSettings, which pydantic 2 moved to pydantic-settings."""
from pydantic import BaseSettings


class Settings(BaseSettings):
    environment: str = "dev"
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
    # B: a newer pydantic, and this service imports the settings module that needs the removed pydantic 1 API
    "billing-svc/B": ("pydantic==2.7.4\n", "acme_models.settings"),
    # G: the two consumers differ only in `requests`, which is not in the artifact's closure
    "orders-svc/G": ("pydantic==1.10.13\nflask==2.2.2\nwerkzeug==2.2.3\nrequests==2.31.0\n", "acme_models.customer"),
    "billing-svc/G": ("pydantic==1.10.13\nflask==2.2.2\nwerkzeug==2.2.3\nrequests==2.32.3\n", "acme_models.customer"),
}
# Projects that must NOT be related to the artifact: they never depend on acme-models.
BYSTANDERS = {
    "marketing-site/G": ("pydantic==2.7.4\nrequests==2.32.3\n", "unrelated project (hygiene control)"),
    "legacy-web/L": ("pydantic==2.7.4\n", "has its own look-alike CustomerRequest (suspected twin control)"),
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


for key, (reqs, note) in BYSTANDERS.items():
    name, sc = key.split("/")
    put(f"{key}/requirements.txt", reqs)
    put(f"{key}/requirements.in", reqs)
    put(f"{key}/README.md", f"# {name} (Faultline fixture, scenario {sc})" + chr(10) + chr(10) + f"{note}." + chr(10))
    put(f"{key}/app/__init__.py", "")
put("legacy-web/L/pyproject.toml", '''
[project]
name = "legacy-web"
version = "0.4.0"
dependencies = ["pydantic>=2"]
''')
put("legacy-web/L/app/models.py", '''
from pydantic import BaseModel


class CustomerRequest(BaseModel):
    """A look-alike: same name and similar fields, but NOT the shared artifact."""
    customer_id: int
    email: str
    loyalty_points: int = 0
''')


# ----------------------------------------------------------------------------- scenario C: a signature change that only call-site checking sees
# A separate small artifact: adding urllib3 to the shared acme-models reference world would change every other scenario (see docs/adr/0004).
put("acme-http/pyproject.toml", '''
[project]
name = "acme-http"
version = "0.1.0"
description = "HTTP retry policies shared by the demo services (Faultline fixture, scenario C)"
requires-python = ">=3.9"
dependencies = ["urllib3>=1.26"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_http"]
''')
put("acme-http/src/acme_http/__init__.py", '''
"""HTTP retry policies. Pure Python."""
__version__ = "0.1.0"
''')
put("acme-http/src/acme_http/retry.py", '''
"""Retry policies. Importing this module works with every urllib3; one of the calls below does not."""
from urllib3.util.retry import Retry


def make_retry():
    """Retry GET three times. method_whitelist was renamed allowed_methods in urllib3 1.26 and removed in urllib3 2.0."""
    return Retry(total=3, method_whitelist=["GET"])


def make_quick_retry():
    """Uses only keywords that exist in every urllib3 version: it must never be reported."""
    return Retry(total=2, backoff_factor=0.1)
''')
put("acme-http/requirements.in", """
# Reference world of scenario C: the urllib3 the artifact was written against.
urllib3==1.26.20
""")
put("acme-http/README.md", """
# acme-http (Faultline fixture, scenario C)

`requirements.lock.txt` is the reference world. Hand verification: fixtures/verification/C.md.
""")
put("orders-svc/C/requirements.in", "urllib3==2.2.3\n")
put("orders-svc/C/requirements.txt", "urllib3==2.2.3\nacme-http @ git+https://github.com/faultline-demo/acme-http@scenario-C\n")
put("orders-svc/C/app/main.py", '''
"""orders-svc (Faultline fixture, scenario C). Uses the shared HTTP retry policies."""
import acme_http.retry as shared

print("loaded", shared.__name__)
''')
put("orders-svc/C/README.md", "# orders-svc (Faultline fixture, scenario C)\n\n`requirements.lock.txt` is the resolved world (urllib3 2.x).\n")
C_KEYS = ("acme-http", "orders-svc/C")

# ----------------------------------------------------------------------------- scenarios J and E: data contracts (pydantic 1 produces, pydantic 2 parses)
# A separate artifact for the same reason as acme-http: pydantic is already in the acme-models reference world, and its models there
# must stay as they are (docs/adr/0006).
put("acme-contracts/pyproject.toml", '''
[project]
name = "acme-contracts"
version = "0.1.0"
description = "Wire models shared by the demo services (Faultline fixture, scenarios J and E)"
requires-python = ">=3.9"
dependencies = ["pydantic>=1.10,<3"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_contracts"]
''')
put("acme-contracts/src/acme_contracts/__init__.py", '''
"""Wire models. Importing them works with pydantic 1 and 2; what they accept on the wire is not the same."""
__version__ = "0.1.0"
''')
put("acme-contracts/src/acme_contracts/customer.py", '''
"""The customer request that orders-svc sends and billing-svc parses (scenario J)."""
from typing import Optional

from pydantic import BaseModel


class CustomerRequest(BaseModel):
    customer_id: int
    email: str
    middle_name: Optional[str]         # no default: optional in pydantic 1, required in pydantic 2


class LoyaltyNote(BaseModel):
    """Negative control: every field has a default, so both pydantic versions accept the same payloads."""
    note: Optional[str] = None
    points: int = 0
''')
put("acme-contracts/src/acme_contracts/ids.py", '''
"""A reference that may be a number or text (scenario E)."""
from typing import Union

from pydantic import BaseModel


class Ref(BaseModel):
    value: Union[int, str]             # pydantic 1 tries int first, so "42" becomes 42; pydantic 2 keeps "42" as text
''')
put("acme-contracts/fixtures/ref_example.json", '{"value": "42"}\n')
put("acme-contracts/requirements.in", """
# Reference world of scenarios J and E: the pydantic the models were written against.
pydantic==1.10.13
""")
put("acme-contracts/README.md", """
# acme-contracts (Faultline fixture, scenarios J and E)

`requirements.lock.txt` is the reference world. Hand verification: fixtures/verification/J.md and E.md.
""")
for _sc, _mod in (("J", "customer"), ("E", "ids")):
    put(f"billing-svc/{_sc}/requirements.in", "pydantic==2.7.4\n")
    put(f"billing-svc/{_sc}/requirements.txt", f"pydantic==2.7.4\nacme-contracts @ git+https://github.com/faultline-demo/acme-contracts@scenario-{_sc}\n")
    put(f"billing-svc/{_sc}/app/main.py", f'''
"""billing-svc (Faultline fixture, scenario {_sc}). Parses the wire models the other services send."""
import acme_contracts.{_mod} as models

print("loaded", models.__name__)
''')
    put(f"billing-svc/{_sc}/README.md", f"# billing-svc (Faultline fixture, scenario {_sc})\n\n`requirements.lock.txt` is the resolved world (pydantic 2.x).\n")
CONTRACT_KEYS = ("acme-contracts", "billing-svc/J", "billing-svc/E")


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
    only_c = "--only-c" in sys.argv[1:]            # write just scenario C and leave every other fixture byte untouched
    only_contracts = "--only-contracts" in sys.argv[1:]      # likewise for scenarios J and E
    wanted = {k: v for k, v in FILES.items() if k.startswith(C_KEYS)} if only_c else         {k: v for k, v in FILES.items() if k.startswith(CONTRACT_KEYS)} if only_contracts else FILES
    for rel, text in wanted.items():
        p = REPOS / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    if only_contracts:
        for d in ("acme-contracts", "billing-svc/J", "billing-svc/E"):
            compile_lock(REPOS / d / "requirements.in", REPOS / d / "requirements.lock.txt")
        print(f"wrote scenarios J and E: {len(wanted)} files and 3 lock files")
        return 0
    compile_lock(REPOS / "acme-http" / "requirements.in", REPOS / "acme-http" / "requirements.lock.txt")
    compile_lock(REPOS / "orders-svc" / "C" / "requirements.in", REPOS / "orders-svc" / "C" / "requirements.lock.txt")
    if only_c:
        print(f"wrote scenario C: {len(wanted)} files and 2 lock files")
        return 0
    art = REPOS / "acme-models"
    compile_lock(art / "requirements.in", art / "requirements.lock.txt")
    compile_lock(art / "requirements.test.in", art / "requirements.test.lock.txt")
    for key in (*CONSUMERS, *BYSTANDERS):
        d = REPOS / key
        compile_lock(d / "requirements.in", d / "requirements.lock.txt")
    # the .in files are inputs for locking only; keep them next to the locks for reproducibility
    print(f"wrote {len(FILES)} files and {2 + len(CONSUMERS)} lock files under {REPOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
