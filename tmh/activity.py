"""Analysis activity log: what was run, found and decided, in order.

Every tmh command appends one line to .tmh/activity.jsonl, and agents add their
own milestones with `tmh note`. The report turns this into the "分析过程" timeline
so developers can follow how a conclusion was reached, not only the conclusion.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import tmh_dir

KINDS = ("command", "finding", "decision", "question", "change", "verify")


def log(root: Path, kind: str, text: str, **extra) -> None:
    x = tmh_dir(root)
    if not x.is_dir():
        return
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "text": text}
    rec.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
    try:
        with (x / "activity.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read(root: Path) -> list[dict]:
    p = tmh_dir(root) / "activity.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
