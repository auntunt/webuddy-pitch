"""Owner's executor page data: installed state, last connection test, and usage from our own run records.

Tokens are shown only when a run record already stores them; none are estimated.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from . import executor_setup
from .store import now

TESTS = "agent-tests.json"


def record_test(data_dir, name: str, result: dict) -> None:
    path = Path(data_dir) / TESTS
    tests = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    tests[name] = {"at": now(), "ok": bool(result.get("ok")), "reason": str(result.get("reason") or result.get("error") or "")}
    path.write_text(json.dumps(tests, ensure_ascii=False, indent=1), encoding="utf-8")


def _seconds(start: str, end: str) -> float | None:
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (TypeError, ValueError):
        return None


def usage(store, days: int = 7) -> dict:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = store.q("SELECT agent,status,exit_code,created,started,ended FROM runs WHERE mode!='ask' AND created>=? ORDER BY id", (cutoff,))
    out: dict = {}
    for r in rows:
        u = out.setdefault(r["agent"], {"runs": 0, "success": 0, "last_used": "", "total_seconds": 0.0})
        u["runs"] += 1
        if r["status"] == "done" and r["exit_code"] in (0, None):
            u["success"] += 1
        u["last_used"] = max(u["last_used"], r["ended"] or r["created"] or "")
        sec = _seconds(r["started"], r["ended"]) if r["started"] and r["ended"] else None
        u["total_seconds"] += sec or 0.0
    for u in out.values():
        u["success_rate"] = round(u["success"] / u["runs"], 2) if u["runs"] else None
        u["total_seconds"] = round(u["total_seconds"])
    return {"days": days, "by_executor": out}


def view(P) -> dict:
    from . import agents
    scanned = executor_setup.scan()
    conf = agents.load_config(P.data_dir)
    path = Path(P.data_dir) / TESTS
    tests = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    executors = []
    for name, c in conf.items():
        engine = agents.engine_name(name, c)
        if engine not in ("codex", "claude", "cursor"):
            continue
        found = scanned.get(engine, {})
        executors.append({"name": name, "title": c.get("title", name), "engine": engine,
                          "installed": bool(found.get("executables") or c.get("bin")),
                          "version": found.get("version", ""), "path": (found.get("executables") or [""])[0],
                          "last_test": tests.get(name)})
    return {"executors": executors, "usage": usage(P.store)}
