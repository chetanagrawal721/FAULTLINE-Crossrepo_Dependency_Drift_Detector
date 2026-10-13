"""Write the OpenAPI document to frontend/openapi.json (deterministic, no server needed).

    python scripts/export_openapi.py            # write
    python scripts/export_openapi.py --check    # exit 1 if the committed file is stale
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from faultline.api.main import create_app  # noqa: E402
from faultline.core.config import Settings  # noqa: E402
from faultline.core.enums import Mode  # noqa: E402

TARGET = ROOT / "frontend" / "openapi.json"


def render() -> str:
    tmp = Path(tempfile.gettempdir())
    app = create_app(Settings(db_path=tmp / "x.db", store_path=tmp / "s", mode=Mode.FIXTURE, admin_token=None,
                              lease_seconds=1, heartbeat_seconds=1, poll_seconds=1))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print("frontend/openapi.json is stale: run `python tools/fl.py gen-types`")
            sys.exit(1)
        print("openapi.json is current")
    else:
        TARGET.write_text(text, encoding="utf-8")
        print(f"wrote {TARGET}")
