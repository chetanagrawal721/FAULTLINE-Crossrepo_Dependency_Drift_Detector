"""Reproduce, outside Faultline, every third-party behaviour the fixtures depend on (milestone M1.0).

For each scenario it builds two plain virtual environments with `uv` (wheels only), runs the same command three
times in each, and records exit codes and the first line of the error. Output: fixtures/verification/results.json
and one markdown record per scenario. If a claim is false, replace the example. Never change the expected verdict.

    python scripts/verify_fixture_facts.py            # needs network access to PyPI
"""
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "verification"

CUSTOMER_REQUEST = '''
import sys, pydantic
from typing import Optional
from pydantic import BaseModel
class CustomerRequest(BaseModel):
    customer_id: int
    middle_name: Optional[str]
    loyalty_points: int = 0
payload = '{"customer_id": 1, "loyalty_points": 0}'     # bytes a v1 producer sends with exclude_none=True
if pydantic.VERSION.startswith("1"):
    out = CustomerRequest(customer_id=1, middle_name=None).json(exclude_none=True)
    assert out == payload, out
    CustomerRequest.parse_raw(payload)
else:
    CustomerRequest.model_validate_json(payload)
print("accepted")
'''

UNION = '''
import pydantic
from typing import Union
from pydantic import BaseModel
class Ref(BaseModel):
    value: Union[int, str]
raw = '{"value": "42"}'
v = Ref.parse_raw(raw).value if pydantic.VERSION.startswith("1") else Ref.model_validate_json(raw).value
print(type(v).__name__, repr(v))
'''

SCENARIOS = [
    {"id": "D", "title": "Transitive world drift: Flask 2.2.2 imports werkzeug.urls.url_quote, removed in Werkzeug 3",
     "ref": ["flask==2.2.2", "werkzeug==2.2.3"], "test": ["flask==2.2.2", "werkzeug==3.0.6"],
     "code": "import flask; print('ok', flask.__version__)",
     "ref_expect": "ok 2.2.2", "test_expect_error": "cannot import name 'url_quote' from 'werkzeug.urls'"},
    {"id": "B", "title": "API removed: pydantic.BaseSettings moved out of pydantic in v2",
     "ref": ["pydantic==1.10.13"], "test": ["pydantic==2.7.4"],
     "code": "from pydantic import BaseSettings; print('ok')",
     "ref_expect": "ok", "test_expect_error": "BaseSettings` has been moved to the `pydantic-settings` package"},
    {"id": "C", "title": "Signature changed: urllib3 2.x removed Retry(method_whitelist=...)",
     "ref": ["urllib3==1.26.18"], "test": ["urllib3==2.0.7"],
     "code": "from urllib3.util.retry import Retry; Retry(total=3, method_whitelist=['GET']); print('ok')",
     "ref_expect": "ok", "test_expect_error": "unexpected keyword argument 'method_whitelist'"},
    {"id": "H", "title": "Harmless drift: pydantic .dict() still works in v2 (deprecated, warns)",
     "ref": ["pydantic==1.10.13"], "test": ["pydantic==2.7.4"],
     "code": "from pydantic import BaseModel\nclass M(BaseModel):\n    a: int\nprint(M(a=1).dict())",
     "ref_expect": "{'a': 1}", "test_expect_ok": "{'a': 1}"},
    {"id": "J", "title": "Data contract: Optional field without a default is required in pydantic v2",
     "ref": ["pydantic==1.10.13"], "test": ["pydantic==2.7.4"],
     "code": CUSTOMER_REQUEST, "ref_expect": "accepted", "test_expect_error": "middle_name"},
    {"id": "E", "title": "Silent divergence: Union[int, str] parses '42' as int in v1 and keeps str in v2",
     "ref": ["pydantic==1.10.13"], "test": ["pydantic==2.7.4"],
     "code": UNION, "ref_expect": "int 42", "test_expect_ok": "str '42'"},
]


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def build_env(base: Path, name: str, pins: list[str]) -> tuple[Path, list[str]]:
    env = base / name
    uv = [sys.executable, "-m", "uv"]
    r = sh([*uv, "venv", "--python", "3.12", "-q", str(env)])
    if r.returncode:
        raise SystemExit(f"venv failed: {r.stderr}")
    py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    r = sh([*uv, "pip", "install", "-q", "--python", str(py), "--only-binary", ":all:", *pins])
    if r.returncode:
        raise SystemExit(f"install failed for {pins}: {r.stderr}")
    freeze = sh([*uv, "pip", "freeze", "--python", str(py)]).stdout.strip().splitlines()
    return py, freeze


def run3(py: Path, code: str) -> list[dict]:
    runs = []
    for _ in range(3):
        r = sh([str(py), "-W", "ignore", "-c", code])
        text = (r.stdout + r.stderr).strip()
        last = [ln for ln in text.splitlines() if ln.strip()]
        runs.append({"exit": r.returncode, "stdout": r.stdout.strip(), "last_line": last[-1] if last else "",
                     "text": text[-1500:]})
    return runs


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="fl-verify-"))
    results = []
    try:
        for s in SCENARIOS:
            print(f"== {s['id']}: {s['title']}", flush=True)
            ref_py, ref_freeze = build_env(base, f"{s['id']}-ref", s["ref"])
            test_py, test_freeze = build_env(base, f"{s['id']}-test", s["test"])
            ref_runs, test_runs = run3(ref_py, s["code"]), run3(test_py, s["code"])
            ref_ok = all(r["exit"] == 0 and s["ref_expect"] in r["stdout"] for r in ref_runs)
            if "test_expect_error" in s:
                test_ok = all(r["exit"] != 0 and s["test_expect_error"] in r["text"] for r in test_runs)
            else:
                test_ok = all(r["exit"] == 0 and s["test_expect_ok"] in r["stdout"] for r in test_runs)
            verified = ref_ok and test_ok
            print(f"   reference 3/3 as expected: {ref_ok}; consumer 3/3 as expected: {test_ok}", flush=True)
            results.append({"id": s["id"], "title": s["title"], "verified": verified, "ref_ok": ref_ok,
                            "test_ok": test_ok, "ref_pins": s["ref"], "test_pins": s["test"],
                            "ref_freeze": ref_freeze, "test_freeze": test_freeze,
                            "expected": {k: v for k, v in s.items() if k.startswith(("ref_expect", "test_expect"))},
                            "ref_runs": ref_runs, "test_runs": test_runs})
    finally:
        shutil.rmtree(base, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"verified_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "python": "3.12",
            "platform": sys.platform, "results": results}
    (OUT / "results.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for r in results:
        lines = [f"# Scenario {r['id']}: {r['title']}", "",
                 f"Verified: **{'yes' if r['verified'] else 'NO'}** on {meta['verified_at']} ({meta['platform']}, Python 3.12, wheels only).",
                 "", "Reference world pins: " + ", ".join(r["ref_pins"]),
                 "", "Consumer world pins: " + ", ".join(r["test_pins"]), "",
                 "## Reference environment (3 runs)", ""]
        lines += [f"- exit {x['exit']}: `{x['last_line'][:200]}`" for x in r["ref_runs"]]
        lines += ["", "## Consumer environment (3 runs)", ""]
        lines += [f"- exit {x['exit']}: `{x['last_line'][:240]}`" for x in r["test_runs"]]
        lines += ["", "Full package lists are in results.json. Re-run: `python scripts/verify_fixture_facts.py`."]
        (OUT / f"{r['id']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bad = [r["id"] for r in results if not r["verified"]]
    print("NOT VERIFIED:", bad if bad else "none")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
