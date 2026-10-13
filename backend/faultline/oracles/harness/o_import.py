"""EXEC zone, NO network, run with the WORLD's interpreter (/opt/world/bin/python -P).

Imports each requested module in its own fresh child process, so one failing import cannot affect another and
every result is independent. Reports, per module: pass or the exception with its traceback frames.
Only module names from the control plane are imported; nothing else is executed.
"""
import json
import os
import subprocess
import sys

sys.path.append("/faultline_harness")           # appended last: packages in the world always win over harness files

from common import emit, read_spec  # noqa: E402

MARK = "@@MODULE_RESULT@@"

CHILD = r'''
import importlib, json, os, sys, traceback, warnings
sys.path[:0] = json.loads(os.environ["FL_PATHS"])
MARK = "@@MODULE_RESULT@@"

def frames(tb):
    out = []
    for frame, lineno in traceback.walk_tb(tb):
        code = frame.f_code
        mod = frame.f_globals.get("__name__")
        if code.co_filename == "<string>":
            mod = "faultline_harness"
        out.append({"module": mod, "file": code.co_filename, "line": lineno, "func": code.co_name})
    return out

mod = sys.argv[1]
try:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        importlib.import_module(mod)
    result = {"passed": True, "warnings": [str(w.message)[:300] for w in caught]}
except BaseException as exc:
    result = {"passed": False, "exc_type": type(exc).__name__, "message": str(exc)[:2000],
              "missing": getattr(exc, "name", None), "frames": frames(exc.__traceback__)}
print(MARK + json.dumps(result))
'''


def import_one(module: str, paths: list[str]) -> dict:
    env = {**os.environ, "FL_PATHS": json.dumps(paths)}
    try:
        r = subprocess.run([sys.executable, "-P", "-c", CHILD, module], capture_output=True, text=True,
                           timeout=45, env=env)
    except subprocess.TimeoutExpired:
        return {"entry": module, "passed": False, "exc_type": "TimeoutExpired", "message": "import did not finish in 45 s",
                "frames": [{"module": "faultline_harness"}]}
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(MARK)]
    if not lines:
        return {"entry": module, "passed": False, "exc_type": "ChildCrash",
                "message": (r.stderr or r.stdout)[-500:], "frames": [{"module": "faultline_harness"}]}
    out = json.loads(lines[-1][len(MARK):])
    out["entry"] = module
    return out


def main() -> None:
    args = read_spec().get("args", {})
    modules = args["modules"]
    paths = list(args.get("pythonpath", []))
    emit({"python": sys.version.split()[0], "entries": [import_one(m, paths) for m in modules]})


if __name__ == "__main__":
    main()
