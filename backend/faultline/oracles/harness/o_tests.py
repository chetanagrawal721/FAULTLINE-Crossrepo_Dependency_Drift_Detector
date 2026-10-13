"""EXEC zone, NO network, run with the WORLD's interpreter (/opt/world/bin/python -P).

Runs the artifact's own test suite with pytest and reports one entry per test. Plugin auto-loading is disabled and
no config files are read, so the result depends only on the world, the artifact and the tests.
If pytest is not installed in the world, the harness says so (that is a harness problem, never a compatibility break).
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.append("/faultline_harness")

from common import emit, read_spec  # noqa: E402

FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')


def module_of(path: str) -> str:
    if "/faultline_harness/" in path:
        return "faultline_harness"
    for marker in ("/site-packages/", "/artifact/src/"):
        if marker in path:
            rel = path.split(marker, 1)[1]
            rel = re.sub(r"\.py$", "", rel)
            return re.sub(r"/__init__$", "", rel).replace("/", ".")
    if "/work/tests" in path:
        return "tests." + re.sub(r"\.py$", "", path.split("/work/tests/", 1)[-1]).replace("/", ".")
    return path


def frames_from(text: str) -> list[dict]:
    return [{"module": module_of(f), "file": f, "line": int(n), "func": fn} for f, n, fn in FRAME.findall(text or "")]


def exc_type_of(message: str, text: str) -> str:
    for source in (message or "", (text or "").strip().splitlines()[-1] if (text or "").strip() else ""):
        m = re.match(r"^([\w.]+(?:Error|Exception|Exit|Interrupt|Warning)|assert)\b", source.strip())
        if m:
            return m.group(1).split(".")[-1]
    return "AssertionError" if "assert" in (message or "") else "Exception"


def main() -> None:
    args = read_spec().get("args", {})
    if importlib.util.find_spec("pytest") is None:
        emit({"harness_error": "pytest is not installed in this world: the test overlay is missing", "entries": []})
        return
    src = args.get("tests_dir", "/artifact/tests")
    dst = "/work/tests"
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    env = {**os.environ, "PYTHONPATH": ":".join(args.get("pythonpath", ["/artifact/src"])),
           "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    cmd = [sys.executable, "-P", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "--tb=native",
           "--junitxml=/work/junit.xml", "--rootdir", dst, dst]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=dst)
    if not os.path.exists("/work/junit.xml"):
        emit({"harness_error": "pytest produced no report", "returncode": r.returncode,
              "stderr_tail": (r.stderr or r.stdout)[-800:], "entries": []})
        return
    entries = []
    for tc in ET.parse("/work/junit.xml").getroot().iter("testcase"):
        file_part = (tc.get("classname") or "").replace(".", "/")
        entry = {"entry": f"{file_part}.py::{tc.get('name')}" if file_part else tc.get("name"),
                 "passed": True, "skipped": False}
        bad = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        skip = tc.find("skipped")
        if bad is not None:
            text = bad.text or ""
            msg = bad.get("message") or ""
            mod = re.search(r"No module named '([^']+)'", text)
            etype = exc_type_of(msg, text)
            if msg.startswith(etype + ": "):
                msg = msg[len(etype) + 2:]                  # the exception type is its own field
            entry.update(passed=False, exc_type=etype, message=(msg or text)[:1500],
                         frames=frames_from(text), missing=mod.group(1) if mod else None,
                         collection_error=(tc.find("error") is not None and not tc.get("classname")))
        elif skip is not None:
            entry.update(skipped=True, message=(skip.get("message") or "")[:300])
        entries.append(entry)
    emit({"returncode": r.returncode, "python": sys.version.split()[0], "entries": entries,
          "summary": r.stdout.strip().splitlines()[-1][:200] if r.stdout.strip() else ""})


if __name__ == "__main__":
    main()
