"""Export the real knowledge-base candidates of the example project.

The golden set in ``tests/fixtures/context_golden.json`` must only reference ids
that the knowledge base actually produces, so it is built from this dump rather
than from guesses:

    python benchmarks/export_candidates.py [--out benchmarks/candidates.json]

It copies ``examples/legacy-java-oa`` into a temporary git repo (same recipe as
``tests/test_tmh.py::copy_repo``), runs ``kb.build`` and writes every graph node
and every knowledge page (id, kind, title, summary, domain, file) to JSON.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tmh import kb  # noqa: E402
from tmh.graph import Graph  # noqa: E402

JAVA = ROOT / "examples" / "legacy-java-oa"


def copy_repo(src: Path, prefix: str = "tmh-golden-") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    dst = d / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=dst, check=True)
    return dst


def dump(repo: Path) -> dict:
    kb.build(repo)
    g = Graph(repo)
    try:
        nodes = []
        for n in g.nodes():
            if n["kind"] in ("file", "mod", "ext", "ep", "sm"):
                continue
            data = n.get("data") or {}
            nodes.append({
                "id": n["id"], "kind": n["kind"], "name": n["name"], "label": n["label"],
                "domain": n.get("domain") or "", "file": n.get("file") or "",
                "comment": str(data.get("comment") or "")[:120],
                "trigger": data.get("trigger") or "", "handler": data.get("handler") or "",
                "crud": data.get("crud") or {},
            })
        reg = kb.load_registry(repo)
        pages = []
        for pid, r in sorted(reg.items()):
            p = kb.page_path(repo, pid)
            if not p.exists():
                continue
            page = kb.parse_page(p.read_text(encoding="utf-8"))
            pages.append({
                "id": pid, "title": r.get("title") or page["meta"].get("title") or pid,
                "summary": r.get("summary") or "", "status": r.get("status") or "",
                "stale": bool(r.get("stale")),
            })
        return {"nodes": nodes, "pages": pages,
                "flows": [n["id"] for n in nodes if n["kind"] == "flow"],
                "domains": sorted({n["domain"] for n in nodes if n["domain"]})}
    finally:
        g.db.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "candidates.json"))
    args = ap.parse_args()
    repo = copy_repo(JAVA)
    data = dump(repo)
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("nodes=%d pages=%d flows=%d domains=%s" % (
        len(data["nodes"]), len(data["pages"]), len(data["flows"]), ",".join(data["domains"])))
    print("written: %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
