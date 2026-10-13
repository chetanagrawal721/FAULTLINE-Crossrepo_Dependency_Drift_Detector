"""EXEC zone, NO network, run with the WORLD's interpreter (/opt/world/bin/python -P).

O-bind: for each call site extracted from the artifact, resolve the called symbol in this world and check that the call shape
(positional count and keyword names) still BINDS to the symbol's current signature. The call itself is never made: placeholder values
are bound with inspect.signature(...).bind(...), so nothing the artifact or the package does at call time runs.

Each site is checked in its own fresh child process, so one failing import cannot affect another site.
A site with star arguments has no fixed shape and is reported as skipped (NOT_EXERCISED), never as passed.
"""
import json
import os
import subprocess
import sys

sys.path.append("/faultline_harness")           # appended last: packages in the world always win over harness files

from common import emit, read_spec  # noqa: E402

MARK = "@@BIND_RESULT@@"

CHILD = r'''
import importlib, inspect, json, os, sys, warnings
sys.path[:0] = json.loads(os.environ["FL_PATHS"])
MARK = "@@BIND_RESULT@@"
site = json.loads(os.environ["FL_SITE"])
parts = site["callee"].split(".")
result = None
obj = None
module_name = None
try:
    for i in range(len(parts), 0, -1):                      # the longest importable prefix is the module; the rest are attributes
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mod = importlib.import_module(".".join(parts[:i]))
            module_name = ".".join(parts[:i])
            break
        except ModuleNotFoundError as exc:
            if exc.name and not (".".join(parts[:i])).startswith(exc.name):
                raise                                         # a dependency of the module is missing, not the module itself
            continue
    else:
        raise ModuleNotFoundError("No module named " + repr(parts[0]), name=parts[0])      # the package is not in this world: not applicable, not a break
    obj = mod
    for attr in parts[len(module_name.split(".")):]:
        obj = getattr(obj, attr)
    origin = getattr(obj, "__module__", None) or module_name
    if not callable(obj):
        result = {"passed": False, "exc_type": "TypeError", "message": site["callee"] + " is not callable", "origin": origin}
    else:
        try:
            sig = inspect.signature(obj)
        except (ValueError, TypeError) as exc:
            result = {"skipped": True, "passed": False, "message": "no signature is available for " + site["callee"] + ": " + str(exc)[:200], "origin": origin}
        else:
            args = [object() for _ in range(site["n_positional"])]
            kwargs = {k: object() for k in site["keyword_names"]}
            try:
                sig.bind(*args, **kwargs)
                result = {"passed": True, "signature": str(sig)[:300], "origin": origin}
            except TypeError as exc:
                result = {"passed": False, "exc_type": "TypeError", "message": str(exc)[:500], "origin": origin, "signature": str(sig)[:300]}
except BaseException as exc:
    result = {"passed": False, "exc_type": type(exc).__name__, "message": str(exc)[:500], "origin": module_name or parts[0],
              "missing": getattr(exc, "name", None)}
print(MARK + json.dumps(result))
'''


def check_site(site: dict, paths: list[str]) -> dict:
    entry = "bind:" + site["id"]
    if site.get("has_star_args") or site.get("has_star_kwargs"):
        return {"entry": entry, "passed": False, "skipped": True, "frames": [{"module": site["callee"].rsplit(".", 1)[0]}],
                "message": "star arguments hide the call shape, so it cannot be bound"}
    env = {**os.environ, "FL_PATHS": json.dumps(paths), "FL_SITE": json.dumps(site)}
    try:
        r = subprocess.run([sys.executable, "-P", "-c", CHILD], capture_output=True, text=True, timeout=45, env=env)
    except subprocess.TimeoutExpired:
        return {"entry": entry, "passed": False, "exc_type": "TimeoutExpired", "message": "bind check did not finish in 45 s", "frames": [{"module": "faultline_harness"}]}
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(MARK)]
    if not lines:
        return {"entry": entry, "passed": False, "exc_type": "ChildCrash", "message": (r.stderr or r.stdout)[-500:], "frames": [{"module": "faultline_harness"}]}
    out = json.loads(lines[-1][len(MARK):])
    out["entry"] = entry
    out["frames"] = [{"module": out.pop("origin", None) or site["callee"].rsplit(".", 1)[0]}]     # where the failure originates: the called package
    out["site"] = {k: site[k] for k in ("id", "callee", "n_positional", "keyword_names")}
    return out


def main() -> None:
    args = read_spec().get("args", {})
    paths = list(args.get("pythonpath", []))
    emit({"python": sys.version.split()[0], "entries": [check_site(s, paths) for s in args["sites"]]})


if __name__ == "__main__":
    main()
