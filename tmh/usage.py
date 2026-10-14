"""IDE-side usage: every MCP tool call an agent makes outside the platform, one line in .tmh/usage.jsonl.

The platform counts these toward a ticket's AI participation. A call is tied to a
ticket when its arguments name a key like TOG-12, or when the developer picked the
ticket on the platform ("写入项目" writes .tmh/current-ticket). Calls made by the
platform's own runs carry `run` so they are not counted twice.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .config import tmh_dir

KEY = re.compile(r"\b([A-Z][A-Z0-9]{0,9}-\d+)\b")
FILE = "usage.jsonl"


def current_ticket(root: Path) -> str:
    try:
        return (tmh_dir(root) / "current-ticket").read_text(encoding="utf-8").strip()[:40]
    except OSError:
        return ""


def ticket_of(root: Path, args: dict) -> str:
    for v in (args or {}).values():
        m = KEY.search(v) if isinstance(v, str) else None
        if m:
            return m.group(1)
    return os.environ.get("TMH_TICKET", "") or current_ticket(root)


def log(root: Path, tool: str, args: dict, client: str = "", source: str = "mcp", ok: bool = True) -> None:
    x = tmh_dir(root)
    if not x.is_dir():
        return
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "source": source, "tool": tool, "client": client[:60],
           "ticket": ticket_of(root, args), "ok": ok}
    if os.environ.get("TMH_RUN"):
        rec["run"] = os.environ["TMH_RUN"]
    try:
        with (x / FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def read(root: Path, limit: int = 200000) -> list[dict]:
    p = tmh_dir(root) / FILE
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
