"""Diagnose why platform kb follow-up queues only one flow page after context-pack v2.

Run inside the repo (Linux/WSL or Windows):
    python tools/diag_context_flowids.py
It copies examples/legacy-java-oa into a temp repo, builds the KB, and prints
which flow ids appear in legacy build_context vs context_pack.assemble for the
same ticket text, plus registry status of each id.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tmh import kb  # noqa: E402
from tmh.context import build_context  # noqa: E402
from tmh.context_pack import assemble  # noqa: E402

QUERY = "请假审批通过后状态不对 审批通过以后请假单状态没变"


def main() -> int:
    src = ROOT / "examples" / "legacy-java-oa"
    d = Path(tempfile.mkdtemp(prefix="diag-oa-"))
    repo = d / src.name
    shutil.copytree(src, repo, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=repo, check=True)
    kb.build(repo)
    reg = kb.load_registry(repo)

    legacy = build_context(repo, QUERY, 8000)
    v2 = assemble([{"root": str(repo), "label": "oa", "current": True}], QUERY, budget=8000, log=False)
    pat = re.compile(r"flow:[A-Za-z0-9_.\-]+")
    legacy_ids = sorted(set(pat.findall(legacy)))
    v2_ids = sorted(set(pat.findall(v2)))

    print("registry flow pages:", len([p for p in reg if p.startswith("flow:")]))
    for label, ids in (("legacy", legacy_ids), ("v2", v2_ids)):
        print("\n%s flow ids (%d):" % (label, len(ids)))
        for fid in ids:
            r = reg.get(fid)
            print("  %-40s registry=%s status=%s orphan=%s stale=%s" % (
                fid, "yes" if r else "NO", (r or {}).get("status", "-"), (r or {}).get("orphan"), (r or {}).get("stale")))
    print("\nlegacy-only:", sorted(set(legacy_ids) - set(v2_ids)))
    print("v2-only:", sorted(set(v2_ids) - set(legacy_ids)))
    print("\n--- legacy head ---\n", legacy[:900])
    print("\n--- v2 text (flow lines) ---")
    for line in v2.splitlines():
        if "flow:" in line:
            print(line[:200])
    shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
