"""Migration work-item ledger (.tmh/workitems.json).

A 信创 migration spans weeks and many agent sessions; no context window holds
it. The ledger is the external memory: one item per rule hit-group, with
status and notes that survive across sessions. Re-running `tmh assess` refreshes
hit counts but never erases a human's or agent's status/notes.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config as cfgmod
from .report import WAVE, now

STATUSES = ["todo", "doing", "done", "blocked", "wontfix", "cleared"]


def path(root: Path) -> Path:
    return cfgmod.tmh_dir(root) / "workitems.json"


def load(root: Path) -> list[dict]:
    p = path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save(root: Path, items: list[dict]) -> None:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh(root: Path, scan: dict) -> list[dict]:
    old = {i["id"]: i for i in load(root)}
    files_by_rule: dict[str, dict[str, int]] = {}
    for f in scan["findings"]:
        files_by_rule.setdefault(f["rule"], {})
        files_by_rule[f["rule"]][f["file"]] = files_by_rule[f["rule"]].get(f["file"], 0) + 1
    items = []
    for r in scan["summary"]["by_rule"]:
        iid = r["rule"]
        prev = old.pop(iid, None)
        item = {
            "id": iid, "title": r["title"], "category": r["category"], "wave": WAVE.get(r["category"], 3),
            "severity": r["severity"], "effort": r["effort"], "kb": r["kb"], "hits": r["hits"],
            "files": [{"file": k, "hits": v} for k, v in sorted(files_by_rule.get(iid, {}).items())],
            "status": "todo", "notes": [], "updated": now(),
        }
        if prev:
            item["status"] = prev.get("status", "todo") if prev.get("status") != "cleared" else "todo"
            item["notes"] = prev.get("notes", [])
            if prev.get("hits") != item["hits"]:
                item["notes"].append({"at": now(), "by": "tmh", "text": "命中数 %s → %s" % (prev.get("hits"), item["hits"])})
        items.append(item)
    # Rules that no longer hit anywhere: keep the record, mark evidence-cleared.
    for prev in old.values():
        if prev.get("status") not in ("done", "wontfix", "cleared"):
            prev["notes"] = prev.get("notes", []) + [{"at": now(), "by": "tmh", "text": "重新扫描已无命中"}]
            prev["status"] = "cleared"
        prev["hits"] = 0
        prev["files"] = []
        items.append(prev)
    items.sort(key=lambda i: (i["wave"], {"high": 0, "medium": 1, "low": 2, "info": 3}.get(i["severity"], 9), i["id"]))
    save(root, items)
    return items


def set_status(root: Path, iid: str, status: str, note: str, by: str = "agent") -> dict:
    if status not in STATUSES:
        raise SystemExit("状态必须是: " + ", ".join(STATUSES))
    items = load(root)
    for i in items:
        if i["id"] == iid:
            i["status"] = status
            i["updated"] = now()
            if note:
                i["notes"].append({"at": now(), "by": by, "text": note})
            save(root, items)
            return i
    raise SystemExit("找不到工作项 %s（先运行 tmh assess）" % iid)
