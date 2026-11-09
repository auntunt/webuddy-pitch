"""Playwright webServer entry: seed the fixture (idempotent) then serve it."""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

RUNTIME = HERE / ".runtime"
FIXTURE = RUNTIME / "fixture.json"
PORT = int(os.environ.get("NEXT_E2E_PORT", "8891"))
TOKEN = "e2e-next-token"


def ensure_seed():
    import seed_next
    if FIXTURE.exists():
        return json.loads(FIXTURE.read_text())
    meta = seed_next.seed(seed_next.build_repo())
    return meta


def main():
    meta = ensure_seed()
    os.environ["TMH_TOKEN"] = TOKEN
    from tmh.platform import login
    login.set_user(Path(meta["data"]), "e2e-user", "e2e-pass-123")
    from tmh.platform.server import serve
    print("fixture:", json.dumps({k: meta[k] for k in ("ticket", "ids", "good", "base")}), flush=True)
    return serve(Path(meta["data"]), "127.0.0.1", PORT, meta["user"], brand="E2E Webuddy")


if __name__ == "__main__":
    raise SystemExit(main())
