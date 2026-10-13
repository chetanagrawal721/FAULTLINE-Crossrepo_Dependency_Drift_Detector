"""FETCH zone only: resolve declared requirements with the pinned uv. Wheels only (--no-build); never builds anything.

Output is the compiled, hash-pinned requirement text. Failure classification happens on the control plane.
"""
import os
import subprocess

from common import emit, proxy_env, read_spec

PLATFORM = "x86_64-unknown-linux-gnu"


def main() -> None:
    a = read_spec().get("args", {})
    os.makedirs("/work/in", exist_ok=True)
    with open("/work/in/requirements.in", "w", encoding="utf-8") as f:
        f.write("\n".join(a.get("requirements", [])) + "\n")
    cmd = ["uv", "pip", "compile", "/work/in/requirements.in", "--no-config", "--no-build", "--generate-hashes",
           "--no-header", "--no-annotate", "--color", "never", "--python-version", a.get("python_version", "3.12"),
           "--python-platform", PLATFORM, "--exclude-newer", a["exclude_newer"], "-o", "/work/out.txt"]
    if a.get("constraints"):
        with open("/work/in/constraints.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(a["constraints"]) + "\n")
        cmd += ["-c", "/work/in/constraints.txt"]
    if a.get("no_index"):
        cmd += ["--no-index"]
    else:
        cmd += ["--index-url", a.get("index_url", "https://pypi.org/simple")]
    for fl in a.get("find_links", []):
        cmd += ["--find-links", fl]
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp", "UV_CACHE_DIR": "/tmp/uvcache",
           "LC_ALL": "C.UTF-8", **proxy_env()}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=240)
    ver = subprocess.run(["uv", "--version"], capture_output=True, text=True, env=env).stdout.strip()
    out = ""
    if os.path.exists("/work/out.txt"):
        with open("/work/out.txt", encoding="utf-8") as f:
            out = f.read()
    probes = {p: os.path.exists(p) for p in a.get("probe_paths", [])}
    emit({"returncode": r.returncode, "output": out, "stderr_tail": r.stderr[-3000:], "uv_version": ver, "probes": probes,
          "flags": [c for c in cmd if c.startswith("--")]})


if __name__ == "__main__":
    main()
