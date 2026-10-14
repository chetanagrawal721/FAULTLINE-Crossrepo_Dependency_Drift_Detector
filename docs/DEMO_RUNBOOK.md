# Demo runbook: how to run FAULTLINE in front of the judges

This is the practical companion to `docs/demo_script.md` (what to say). It covers what to start, what to paste, what you will see and what to do when something fails.

## The example

Two real, public repositories, pinned to exact commits:

| Role | Repository | Commit |
|---|---|---|
| Shared library (the artifact) | https://github.com/chetanagrawal721/faultline-fixture-acme-models | 2e072e6 |
| Consumer service | https://github.com/chetanagrawal721/faultline-fixture-notify-svc | 4b09e96 |

The story: `acme-models` pins Flask 2.2.2 and works in its own repository. `notify-svc` uses it but does not pin Werkzeug, so its dependency world resolves Werkzeug 3, which removed `werkzeug.urls.url_quote` that Flask 2.2.2 imports. The library imports in its own world and fails in the consumer's.

What FAULTLINE shows, in order: the two commits it pinned, the relationship with the file and line that proves it, the exact dependency difference (`werkzeug`, `itsdangerous`), a witnessed break (3 of 3 fresh runs pass in the library's world, 3 of 3 fail in the consumer's with the identical `ImportError`), the cause narrowed to `werkzeug` by a two-sided search, a verified fix as a diff (`werkzeug<3`), and an evidence bundle anyone can check.

The repositories are fixtures built for this purpose; they say so in their descriptions. The same pipeline runs on any public GitHub repositories you paste.

## Three more examples, one for each other kind of finding

All five repositories are public under `https://github.com/chetanagrawal721/`. Paste the artifact first, then the consumer. Times are real runs of `scripts/demo_check.py`, with warm caches.

| Story | Artifact | Consumer | What the judges see | Time |
|---|---|---|---|---|
| **Import break** (the main example above) | `faultline-fixture-acme-models` | `faultline-fixture-notify-svc` | BREAK WITNESSED: `ImportError: cannot import name url_quote`, from the import check and from the library's own test `test_web.py::test_show_customer`; cause `werkzeug` | about 100 s |
| **Call-site break**: the library still passes a keyword that urllib3 2 removed. It imports fine; only the call fails | `faultline-fixture-acme-http` | `faultline-fixture-orders-svc` | BREAK WITNESSED at `retry.py:7`, `Retry(total=..., method_whitelist=...)` no longer binds; the call that still binds is exercised and not reported; cause `urllib3` | about 50 s |
| **Data-contract break**: pydantic 1 writes a payload, pydantic 2 rejects it | `faultline-fixture-acme-contracts` | `faultline-fixture-billing-svc-contract` | BREAK WITNESSED: the exact bytes `{"customer_id": 0, "email": ""}` are rejected with `middle_name: Field required`; cause `pydantic` | about 2 min |
| **Silent divergence**: both worlds accept the data and read it differently | `faultline-fixture-acme-contracts` | `faultline-fixture-billing-svc-union` | SILENT DIVERGENCE WITNESSED: `reference=42, consumer="42"`, both values shown | about 100 s |

Suggested order for a five-minute slot: paste the main example live (it has the fix and the evidence bundle), then the call-site pair to show that a clean import is not enough. Keep the other two, and the showcase result, for questions.

`python scripts/demo_check.py --case all` runs all five back to back (about 14 minutes). `--case callsite`, `--case contract`, `--case union` and `--case showcase` run one.

### The one-paste showcase

Three repositories under `https://github.com/chetanagrawal721/`: the producer `faultline-fixture-acme-showcase`, the consumer `faultline-fixture-fulfilment-svc` (newer Werkzeug, urllib3 and pydantic, uses all four modules) and the control consumer `faultline-fixture-reporting-svc` (exactly the producer's own versions). One submission shows an import break, a call-site break, a data-contract break, a silent divergence (four witnesses from three oracles in one finding) and a cell with no drift and nothing to run.

It attributes four witnesses one after another, so it takes **405 s the first time and 332 s with every world already built**. That is too long to wait through live. Use it like this: run `python scripts/demo_check.py --case showcase` before you go on stage, leave the finding it prints open in **Findings**, and say that it is a recorded run of the same pipeline. Paste the main pair live (about 100 seconds).

## Before the demo (once, online, on the demo machine and the backup machine)

1. Start Docker Desktop and wait until it says it is running.
2. In the repository folder:
   ```bash
   python scripts/build_images.py        # the sandbox image, pinned by digest
   python scripts/warm_caches.py         # local mirrors of the fixtures and every fixture world built offline
   python tools/fl.py up --detach        # API, worker and sandbox daemon, with the built interface
   python scripts/demo_check.py          # the full rehearsal below, with the clock on it
   python scripts/export_replay.py       # the recorded-evidence pack for the Docker-down fallback
   ```
3. If `demo_check.py` ends with **Ready to demo.**, everything the demo needs works. If it ends with failed checks, each failure line says what to do.

`demo_check.py` is not a mock. It submits the two repositories above through the same HTTP API the interface uses, waits for the real analysis (about one minute), and checks the verdict, the delta, the six fresh runs, the attribution and the bundle.

GitHub allows 60 unauthenticated API calls an hour. Before rehearsing a lot, set a token in the shell that starts the server: `set GITHUB_TOKEN=...` (Windows) or `export GITHUB_TOKEN=...`. The token is used by the control plane only and is never passed into a container.

## Starting it

```bash
python tools/fl.py up --detach          # then open http://127.0.0.1:8000/
python scripts/demo_check.py --preflight   # four seconds: Docker, sandbox, oracles, GitHub
python tools/fl.py down                 # stop everything
```

After any code change, run `python tools/fl.py down` and `up` again. A server started before a change keeps running the old code, and the preflight will say so (for example, an oracle shown as not enabled).

## In the browser

1. Open http://127.0.0.1:8000/ and press **Open the workspace**. The badge in the header and the line under the page title state the mode you are claiming. Say it out loud.
2. **New analysis**: paste the two URLs above, **Pin repositories**, tick the confirmation, **Run analysis**. The run page follows the real job.
3. When it finishes: **Overview** (outcome chart and funnel), **World matrix** (opens on the witnessed cell), **Findings** and the finding, **Open witness** (the six runs and the failure signature), the attribution under the World matrix, **Inventory graph** (select a node to see what it connects to), **Evidence** (the bundle and its integrity check).
4. For a result with no waiting, open **Findings** and the existing recorded run of the same pair.

## The three fallbacks

| What fails | What to do | What the screen says |
|---|---|---|
| GitHub or the network | FIXTURE mode from the local mirror (`var/mirror`) and the warm wheel cache | the FIXTURE badge; say that the network is off and this is the warmed fixture mode |
| Docker | `FAULTLINE_MODE=REPLAY FAULTLINE_DB=var/replay/faultline.db FAULTLINE_STORE=var/replay/store python -m uvicorn faultline.api.main:app_factory --factory --port 8001` | the RECORDED badge; Re-run is disabled with the reason |
| A live run is slow | show the earlier run of the same pair, then the why-path | the mode stored with that record |

## If a check fails

| Symptom | Likely cause | Fix |
|---|---|---|
| "the API answers" fails | the stack is not running | `python tools/fl.py up --detach` |
| "sandbox boundary is verified" fails | Docker Desktop is not running or the image is missing | start Docker; `python scripts/build_images.py` |
| an oracle is "not enabled" | the server is older than the code | `python tools/fl.py down` then `up --detach` |
| "GitHub serves ..." fails | no network or the rate limit is used up | set `GITHUB_TOKEN`, or use the fallbacks above |
| the analysis stays RUNNING | a world is being built for the first time | wait; `warm_caches.py` removes this wait |
