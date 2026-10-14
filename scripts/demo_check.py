"""Preflight and end-to-end rehearsal of the demo, through the same HTTP API the interface uses.

    python scripts/demo_check.py                 # preflight, then the hero case on the published repositories
    python scripts/demo_check.py --preflight     # only the checks (Docker, sandbox, API, GitHub)
    python scripts/demo_check.py --case hero     # a named case from CASES below

Each case submits two real public repositories, waits for the real analysis, and checks the outcome against what the demo script says.
Nothing is mocked: this is the run you would do in front of the judges, with the clock on it. Exit status 1 if anything differs.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
HERO_ARTIFACT = "https://github.com/chetanagrawal721/faultline-fixture-acme-models"
HERO_CONSUMER = "https://github.com/chetanagrawal721/faultline-fixture-notify-svc"
OWNER = "https://github.com/chetanagrawal721/faultline-fixture-"
CASES = {
    "showcase": {
        "title": "One library, two consumers, one paste: an import break, a call-site break, a data-contract break, a silent divergence and a control with nothing to run",
        "repos": [OWNER + "acme-showcase", OWNER + "fulfilment-svc", OWNER + "reporting-svc"],
        "verdict": "BREAK_WITNESSED",
        "delta": {"werkzeug", "urllib3", "pydantic"},
        "cause": [],
        "says": "acme_showcase",
        "min_witnesses": 4,
        "oracles": {"o_import", "o_bind", "o_contract"},
        "control": True,
    },
    "callsite": {
        "title": "A library keeps calling a keyword that urllib3 2 removed. It imports fine; only the call fails",
        "repos": [OWNER + "acme-http", OWNER + "orders-svc"],
        "verdict": "BREAK_WITNESSED",
        "delta": {"urllib3"},
        "cause": ["urllib3"],
        "says": "method_whitelist",
    },
    "contract": {
        "title": "A payload that pydantic 1 produces is rejected by a pydantic 2 consumer",
        "repos": [OWNER + "acme-contracts", OWNER + "billing-svc-contract"],
        "verdict": "BREAK_WITNESSED",
        "delta": {"pydantic"},
        "cause": ["pydantic"],
        "says": "middle_name: Field required",
    },
    "union": {
        "title": "Both worlds accept the data, but they read it differently: the text 42 becomes a number in one",
        "repos": [OWNER + "acme-contracts", OWNER + "billing-svc-union"],
        "verdict": "SILENT_DIVERGENCE_WITNESSED",
        "delta": {"pydantic"},
        "cause": ["pydantic"],
        "says": 'reference=42, consumer="42"',
    },
    "hero": {
        "title": "A shared library that imports fine alone and fails under a consumer's dependencies (Flask 2.2.2 with Werkzeug 3)",
        "repos": [HERO_ARTIFACT, HERO_CONSUMER],
        "verdict": "BREAK_WITNESSED",
        "delta": {"werkzeug"},
        "cause": ["werkzeug"],
        "says": "cannot import name 'url_quote'",
        "min_witnesses": 2,
        "oracles": {"o_import", "o_tests"},                  # the import fails, and so does the library's own web test
    },
}


def call(method: str, path: str, body: dict | None = None, token: str | None = None, timeout: int = 60):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Accept": "application/json", "Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"{method} {path} -> {e.code}: {detail}") from None


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def ok(self, label: str, detail: str = "") -> None:
        print(f"  ok    {label}{('  ' + detail) if detail else ''}")

    def bad(self, label: str, detail: str = "") -> None:
        self.failed += 1
        print(f"  FAIL  {label}{('  ' + detail) if detail else ''}")

    def check(self, cond: bool, label: str, detail: str = "") -> None:
        (self.ok if cond else self.bad)(label, detail)


def preflight(r: Report) -> dict | None:
    print("Preflight")
    try:
        h = call("GET", "/api/health", timeout=10)
    except (SystemExit, urllib.error.URLError, OSError) as e:
        r.bad("the API answers", f"{e}. Start it with: python tools/fl.py up")
        return None
    r.check(h.get("status") == "ok" and h.get("db") == "ok", "the API and database are healthy", f"mode {h.get('mode')}, schema v{h.get('schema_version')}")
    caps = call("GET", "/api/capabilities")
    sb = caps["sandbox"]
    r.check(bool(sb["verified"]), "the sandbox boundary is verified (Docker is up)", sb["reason"])
    for name in ("o_import", "o_bind", "o_contract"):
        r.check(caps["oracles"][name]["state"] == "enabled", f"oracle {name} is enabled")
    r.check(caps["features"]["witness_verification"]["state"] == "enabled", "witness verification is enabled")
    # the rate limit is read from the free endpoint; the repositories are checked with git, which does not use the API quota
    try:
        core = json.load(urllib.request.urlopen(urllib.request.Request("https://api.github.com/rate_limit", headers={"User-Agent": "faultline-demo-check"}), timeout=15))["resources"]["core"]
        mins = max(0, int((core["reset"] - time.time()) / 60))
        enough = core["remaining"] >= 30
        (r.ok if enough else r.bad)("GitHub API quota for this machine", f"{core['remaining']} of {core['limit']} calls left, resets in {mins} min" + ("" if enough or core["limit"] > 60 else ". Start the server with GITHUB_TOKEN set (60 an hour is not enough to rehearse)"))
    except Exception as e:  # noqa: BLE001
        r.bad("GitHub API is reachable", f"{type(e).__name__}: {e}. Use FIXTURE mode from the local mirror, or the REPLAY pack")
    for repo in sorted({u for c in CASES.values() for u in c["repos"]}):
        ok = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", repo + ".git"], capture_output=True, timeout=60, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}).returncode == 0
        r.check(ok, f"GitHub serves {repo.rsplit('/', 1)[1]}")
    return h


def add_repository(project_id: str, url: str, token: str | None, attempts: int = 4):
    """GitHub sometimes answers 5xx for a moment (a new repository, a busy edge). The API marks those retryable; so does this."""
    for i in range(attempts):
        try:
            return call("POST", f"/api/projects/{project_id}/repositories", {"url": url, "ref": None}, token, timeout=300)
        except SystemExit as e:
            if "retryable" not in str(e) or i == attempts - 1:
                raise
            time.sleep(4 * (i + 1))


def run_case(r: Report, name: str, token: str | None) -> None:
    case = CASES[name]
    print(f"\nCase '{name}': {case['title']}")
    t0 = time.time()
    p = call("POST", "/api/projects", {"name": f"demo check · {name} · {time.strftime('%H:%M:%S')}"}, token)
    ids = []
    for url in case["repos"]:
        repo = add_repository(p["id"], url, token)
        r.check(bool(repo.get("pinned_sha")), f"pinned {url.rsplit('/', 1)[1]}", f"commit {str(repo.get('pinned_sha'))[:10]}")
        ids.append((url, repo["id"]))
    for url, rid in ids:                                              # fetching happens in the sandbox, as a background job
        while True:
            repo = call("GET", f"/api/repositories/{rid}")
            if repo["status"] in ("INGESTED", "FAILED") or time.time() - t0 > 600:
                break
            time.sleep(2)
        r.check(repo["status"] == "INGESTED", f"fetched {url.rsplit('/', 1)[1]} in the sandbox", f"{repo['status']}, {int(time.time() - t0)} s")
        if repo["status"] != "INGESTED":
            return
    job = call("POST", f"/api/projects/{p['id']}/analyze", None, token)
    last = ""
    while job["status"] in ("QUEUED", "RUNNING"):
        time.sleep(3)
        job = call("GET", f"/api/jobs/{job['job_id']}")
        msg = f"{job['status']} {int((job.get('progress') or 0) * 100)}% {job.get('message') or ''}"
        if msg != last:
            print(f"        {msg}")
            last = msg
        if time.time() - t0 > 900:
            r.bad("the analysis finished within 15 minutes")
            return
    r.check(job["status"] == "DONE", "the analysis job finished", f"{job['status']} in {int(time.time() - t0)} s")
    if job["status"] != "DONE":
        return
    a = call("GET", f"/api/projects/{p['id']}/analysis")
    cell = next((c for c in a["cells"] if c.get("verdict")), None)
    r.check(cell is not None, "a finding was produced")
    if cell is None:
        return
    r.check(cell["verdict"] == case["verdict"], f"verdict is {case['verdict']}", cell["verdict"])
    delta = {d["name"] for d in cell["delta"]}
    r.check(case["delta"] <= delta, "the exact delta names the cause", ", ".join(sorted(delta)))
    f = call("GET", f"/api/findings/{cell['finding_id']}")
    r.check(case["says"] in f["headline"], "the scoped statement quotes the real failure", f["headline"][:140])
    r.check(f["fresh_runs"] >= 6 and f["reused_runs"] == 0, "fresh runs only (6 per oracle), none reused", f"{f['fresh_runs']} fresh, {f['reused_runs']} reused")
    att = cell.get("attribution") or {}
    r.check(set(case["cause"]) <= set(att.get("minimal") or []) and att.get("status") == "COMPLETE" and att.get("sidedness") == "two_sided", "two-sided attribution names the cause", f"{att.get('minimal')} {att.get('status')}")
    if case.get("min_witnesses"):
        ws = f.get("witnesses") or []
        r.check(len(ws) >= case["min_witnesses"], f"{case['min_witnesses']} or more witnesses in one finding", f"{len(ws)} witnesses")
        r.check(case["oracles"] <= {x.get("oracle") for x in ws}, "witnesses from every oracle", ", ".join(sorted({str(x.get('oracle')) for x in ws})))
        if case.get("control"):
            states = sorted(c["state"] for c in a["cells"])
            r.check("NO_DRIFT" in states, "the control consumer shows no drift", ", ".join(states))
    w = f["witnesses"][0]["witness_id"] if f.get("witnesses") else None
    r.check(w is not None, "a witness exists")
    if w:
        m = call("GET", f"/api/witnesses/{w}/bundle/manifest", timeout=120)
        r.check(bool(m["verified"]), "the evidence bundle verifies (hashes, paths, sizes)", f"{len(m['files'])} files")
    print(f"\n  Open it: {BASE}/#/app/finding/{cell['finding_id']}   (total {int(time.time() - t0)} s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--case", choices=sorted(CASES) + ["all"], default="hero")
    ap.add_argument("--token", default=None, help="admin token, when the server requires one")
    a = ap.parse_args()
    r = Report()
    h = preflight(r)
    if h is not None and not a.preflight and r.failed == 0:
        if h.get("mode") == "REPLAY":
            r.bad("the server can start work", "it is in REPLAY mode")
        else:
            for name in (["hero", "callsite", "contract", "union", "showcase"] if a.case == "all" else [a.case]):
                run_case(r, name, a.token)
    print("\n" + ("Ready to demo." if r.failed == 0 else f"{r.failed} check(s) failed. Fix them before presenting."))
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
