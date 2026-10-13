"""EXEC zone: report what a built world actually contains (read-only mount of /opt/world)."""
import json
import subprocess

from common import emit

CODE = (
    "import json, sys, importlib.metadata as m\n"
    "print(json.dumps({'python': sys.version.split()[0], "
    "'packages': sorted([d.metadata['Name'], d.version] for d in m.distributions())}))\n"
)


def main() -> None:
    marker = None
    try:
        marker = json.load(open("/opt/world/.faultline-world", encoding="utf-8"))
    except (OSError, ValueError):
        pass
    r = subprocess.run(["/opt/world/bin/python", "-I", "-c", CODE],
                       capture_output=True, text=True)
    info = None
    if r.returncode == 0:
        try:
            info = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            info = None
    emit({"returncode": r.returncode, "info": info, "marker": marker, "stderr_tail": r.stderr[-500:]})


if __name__ == "__main__":
    main()
