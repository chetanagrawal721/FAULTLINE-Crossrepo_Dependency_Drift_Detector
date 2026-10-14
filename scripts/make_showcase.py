"""Write the showcase fixtures: ONE artifact and TWO consumers that, together, show every kind of finding in a single submission.

    python scripts/make_showcase.py

  acme-showcase   the shared library. Four small modules, each written against the old dependency versions:
                    web.py       imports Flask 2.2.2, which imports a Werkzeug function that Werkzeug 3 removed      -> import break
                    retry.py     calls urllib3 Retry(method_whitelist=...), a keyword urllib3 2 removed               -> call-site break
                    customer.py  a pydantic model whose Optional field has no default (required in pydantic 2)       -> data-contract break
                    ids.py       a pydantic model with Union[int, str] (pydantic 2 keeps "42" as text)                -> silent divergence
  fulfilment-svc  a consumer that resolves Werkzeug 3, urllib3 2 and pydantic 2 and imports all four modules          -> findings
  reporting-svc   a consumer that resolves exactly the library's own dependencies                                     -> no drift (the control)

Pasting the three repositories into one analysis therefore shows, in a single run: relationship discovery with evidence, an exact dependency
delta, three kinds of oracle, witnesses of three kinds, a two-sided attribution for each, a cell with nothing to run, and an evidence bundle.
Locks are resolved by uv with the same cutoff date as every other fixture.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = ROOT / "fixtures" / "repos"
spec = importlib.util.spec_from_file_location("make_fixtures", ROOT / "scripts" / "make_fixtures.py")
mf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mf)

FILES: dict[str, str] = {}


def put(rel: str, text: str) -> None:
    FILES[rel] = text.lstrip("\n")


put("acme-showcase/pyproject.toml", '''
[project]
name = "acme-showcase"
version = "1.0.0"
description = "A shared library whose four modules each depend on something a consumer may resolve differently (Faultline demo fixture)"
requires-python = ">=3.9"
dependencies = ["flask>=2.2", "urllib3>=1.26", "pydantic>=1.10"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/acme_showcase"]
''')
put("acme-showcase/src/acme_showcase/__init__.py", '''
"""A shared library. Importing the package works everywhere; the modules below are where the dependency differences show."""
__version__ = "1.0.0"
''')
put("acme-showcase/src/acme_showcase/web.py", '''
"""A small web app. Flask 2.2.2 imports werkzeug.urls.url_quote, which Werkzeug 3 removed."""
from flask import Flask, jsonify


def make_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
''')
put("acme-showcase/src/acme_showcase/retry.py", '''
"""Retry policies. Importing this module works with every urllib3; one of the calls below does not."""
from urllib3.util.retry import Retry


def make_retry():
    """Retry GET three times. method_whitelist was renamed allowed_methods in urllib3 1.26 and removed in urllib3 2.0."""
    return Retry(total=3, method_whitelist=["GET"])


def make_quick_retry():
    """Uses only keywords that exist in every urllib3 version: it must never be reported."""
    return Retry(total=2, backoff_factor=0.1)
''')
put("acme-showcase/src/acme_showcase/customer.py", '''
"""The customer request that one service sends and another parses."""
from typing import Optional

from pydantic import BaseModel


class CustomerRequest(BaseModel):
    customer_id: int
    email: str
    middle_name: Optional[str]         # no default: optional in pydantic 1, required in pydantic 2


class LoyaltyNote(BaseModel):
    """Every field has a default, so both pydantic versions accept the same payloads: it must never be reported."""
    note: Optional[str] = None
    points: int = 0
''')
put("acme-showcase/src/acme_showcase/ids.py", '''
"""A reference that may be a number or text."""
from typing import Union

from pydantic import BaseModel


class Ref(BaseModel):
    value: Union[int, str]             # pydantic 1 tries int first, so "42" becomes 42; pydantic 2 keeps "42" as text
''')
put("acme-showcase/fixtures/ref_example.json", '{"value": "42"}\n')
put("acme-showcase/requirements.in", """
# The library's own world: the versions its modules were written against.
flask==2.2.2
werkzeug==2.2.3
urllib3==1.26.20
pydantic==1.10.13
""")
put("acme-showcase/README.md", """
# acme-showcase (Faultline demo fixture)

One shared library, four modules, each sensitive to a different dependency. `requirements.lock.txt` is its own world.
""")

CONSUMER_APP = '''
"""{name} (Faultline demo fixture). {what}"""
import acme_showcase.customer as customer
import acme_showcase.ids as ids
import acme_showcase.retry as retry
import acme_showcase.web as web

print("loaded", customer.__name__, ids.__name__, retry.__name__, web.__name__)
'''
put("fulfilment-svc/requirements.in", """
# Resolves newer majors than the library was written against.
flask==2.2.2
urllib3==2.2.3
pydantic==2.7.4
""")
put("fulfilment-svc/requirements.txt", "flask==2.2.2\nurllib3==2.2.3\npydantic==2.7.4\nacme-showcase @ git+https://github.com/faultline-demo/acme-showcase@scenario-S\n")
put("fulfilment-svc/app/main.py", CONSUMER_APP.format(name="fulfilment-svc", what="Uses every module of the shared library, in a world with newer dependencies."))
put("fulfilment-svc/README.md", "# fulfilment-svc (Faultline demo fixture)\n\n`requirements.lock.txt` is the resolved world: Werkzeug 3, urllib3 2, pydantic 2.\n")
put("reporting-svc/requirements.in", """
# Resolves exactly what the library's own world resolves.
flask==2.2.2
werkzeug==2.2.3
urllib3==1.26.20
pydantic==1.10.13
""")
put("reporting-svc/requirements.txt", "flask==2.2.2\nwerkzeug==2.2.3\nurllib3==1.26.20\npydantic==1.10.13\nacme-showcase @ git+https://github.com/faultline-demo/acme-showcase@scenario-S\n")
put("reporting-svc/app/main.py", CONSUMER_APP.format(name="reporting-svc", what="Uses the shared library in exactly the library's own world: nothing differs, so nothing is run."))
put("reporting-svc/README.md", "# reporting-svc (Faultline demo fixture)\n\n`requirements.lock.txt` is the library's own world: the control.\n")


def main() -> int:
    for rel, text in FILES.items():
        p = REPOS / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    for d in ("acme-showcase", "fulfilment-svc", "reporting-svc"):
        mf.compile_lock(REPOS / d / "requirements.in", REPOS / d / "requirements.lock.txt")
    print(f"wrote {len(FILES)} files and 3 lock files under {REPOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
