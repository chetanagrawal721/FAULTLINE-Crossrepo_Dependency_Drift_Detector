"""EXEC zone, no network: read Requires-Dist and Provides-Extra from wheels in the read-only wheelhouse.

Only the METADATA file inside each named wheel is read (a zip member); no wheel code is imported or executed. The control
plane evaluates markers and extras with `packaging`, so this harness stays standard-library only.
"""
import os
import zipfile

from common import emit, read_spec


def main() -> None:
    names = read_spec().get("args", {}).get("files", [])
    out = {}
    for name in names:
        if "/" in name or "\\" in name or name.startswith(".") or not name.endswith(".whl"):
            out[name] = {"error": "unsafe wheel name"}
            continue
        path = os.path.join("/wheelhouse", name)
        try:
            with zipfile.ZipFile(path) as z:
                meta = next((n for n in z.namelist() if n.endswith(".dist-info/METADATA") and n.count("/") == 1), None)
                text = z.read(meta).decode("utf-8", "replace") if meta else ""
        except (OSError, zipfile.BadZipFile) as e:
            out[name] = {"error": f"{type(e).__name__}: {e}"}
            continue
        requires, extras = [], []
        for line in text.splitlines():
            if not line.strip():
                break                                     # headers end at the first blank line
            if line.startswith("Requires-Dist:"):
                requires.append(line.split(":", 1)[1].strip())
            elif line.startswith("Provides-Extra:"):
                extras.append(line.split(":", 1)[1].strip())
        out[name] = {"requires": requires, "extras": extras}
    emit({"metadata": out})


if __name__ == "__main__":
    main()
