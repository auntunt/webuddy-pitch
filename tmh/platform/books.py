"""The sealed baseline and the per-ticket ledger behind the efficiency report.

A before/after comparison is only worth something if "before" was fixed before the work started. So a project's
baseline is sealed once: the time window, the method and every sampled ticket are written down with a hash,
and the file cannot be changed afterwards (a changed file fails its hash and counts as no baseline). Without a
sealed baseline the report shows this period's measured numbers only, no comparison and no saving.

The ledger is one row per ticket handled in the period: cycle, first localisation, rework, AI runs, points, the
points priced in yuan (list price and what was actually paid, kept apart), and how often a person acted on it.
Settings live in <data>/pricing.json next to the point prices:
  {"yuan_per_point": 1.0, "paid_yuan_per_point": 0.6}
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from .errors import ApiError

METHOD = {
    "sample": "从 Jira/禅道导入、在原系统已关闭、且没有在平台上再处理过的工单",
    "cycle": "原系统的创建时间到解决时间（日历时间，不是投入工时）",
    "window": "按原系统的解决时间落在封存窗口内取样",
    "per_person_month": "每月关闭工单数 ÷ 当月有关单的处理人数，再按月平均",
}
MIN_SAMPLE = 20


def bdir(data_dir: Path) -> Path:
    return Path(data_dir) / "baselines"


def _hash(obj: dict) -> str:
    return hashlib.sha256(json.dumps({k: v for k, v in obj.items() if k != "hash"}, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def candidate(store, p: dict, frm: str = "", to: str = "") -> dict:
    """What sealing now would freeze, for the person deciding the window."""
    from .metrics import baseline_stats, history
    rows = [r for r in history(store, p) if (not frm or r["done"][:10] >= frm) and (not to or r["done"][:10] <= to)]
    st = baseline_stats(rows)
    st["warning"] = "样本只有 %d 张，少于 %d 张时对比数波动大" % (len(rows), MIN_SAMPLE) if 0 < len(rows) < MIN_SAMPLE else ""
    return st


def seal(store, data_dir: Path, p: dict, frm: str, to: str, by: str, note: str = "") -> dict:
    from .metrics import baseline_stats, history
    f = bdir(data_dir) / ("%s.json" % p["key"])
    if f.exists():
        old = load_baseline(data_dir, p["key"])
        raise ApiError(409, "基线已于 %s 由 %s 封存，不能再改" % ((old or {}).get("sealed_at", "?"), (old or {}).get("sealed_by", "?")))
    for d in (frm, to):
        if d and not (len(d) == 10 and d[4] == "-" and d[7] == "-"):
            raise ApiError(400, "窗口日期写成 2026-03-01")
    rows = [r for r in history(store, p) if (not frm or r["done"][:10] >= frm) and (not to or r["done"][:10] <= to)]
    if not rows:
        raise ApiError(409, "窗口内没有可作基线的历史工单：先从 Jira 或禅道导入已关闭的工单")
    b = {"version": 1, "project": p["key"], "window": [frm or rows[0]["done"][:10], to or rows[-1]["done"][:10]], "method": METHOD,
         "stats": baseline_stats(rows), "sample": [{"key": (r["t"].get("external") or {}).get("key") or r["t"]["key"], "type": r["t"]["type"],
                                                    "created": r["origin"], "done": r["done"],
                                                    "cycle_h": None if r["cycle"] is None else round(r["cycle"], 2)} for r in rows],
         "sealed_at": time.strftime("%Y-%m-%d %H:%M:%S"), "sealed_by": by, "note": (note or "")[:500]}
    b["hash"] = _hash(b)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        f.chmod(0o444)
    except OSError:
        pass
    return b


def load_baseline(data_dir: Path, key: str) -> dict | None:
    f = bdir(data_dir) / ("%s.json" % key.upper())
    if not f.exists():
        return None
    try:
        b = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {"broken": "基线文件不是合法 JSON（被改过）"}
    if _hash(b) != b.get("hash"):
        return {"broken": "基线文件和封存时的哈希对不上（被改过）", "sealed_at": b.get("sealed_at"), "sealed_by": b.get("sealed_by")}
    return b


def settings(data_dir: Path, pricing: dict | None = None) -> dict:
    conf = {"yuan_per_point": 1.0, "paid_yuan_per_point": None, "yuan_default": True}
    f = Path(data_dir) / "pricing.json"
    if f.exists():
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            j = {}
        for k in ("yuan_per_point", "paid_yuan_per_point"):
            if j.get(k) is not None:
                try:
                    conf[k] = float(j[k])
                except (TypeError, ValueError):
                    pass
        if j.get("yuan_per_point") is not None:
            conf["yuan_default"] = False
    return conf


def packages(data_dir: Path) -> dict:
    """Evidence package status per ticket key, for the ledger."""
    from . import signoff
    d = signoff.edir(data_dir)
    out = {}
    for f in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
        s = signoff.state(data_dir, f.stem)
        dec = s.get("decision") or {}
        out[f.stem] = {"status": s["status"], "label": signoff.STATUS_LABEL[s["status"]], "intact": s["intact"], "missing": len(s["missing"]),
                       "signer": dec.get("signer", ""), "via": dec.get("via", ""), "signed_at": dec.get("ts", ""), "hash": s["hash"]}
    return out
