"""Navigation helpers so an agent can find code by index instead of reading everything.

`where`  — rank files for a set of keywords (requirement words, URL fragments,
           table names, Chinese business terms in comments/labels).
`impact` — reverse lookup for a class / table / file: who references it and
           which entry points sit on top of it.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from . import config as cfgmod
from .fsutil import iter_files, read_text, rel
from .mapper import build_map

SOURCE_SUFFIXES = {".go", ".java", ".cs", ".vb", ".xml", ".jsp", ".aspx", ".ascx", ".cshtml", ".js", ".ts", ".vue", ".html", ".sql", ".properties", ".yml", ".yaml", ".config", ".ftl"}


def load_map(root: Path, rebuild: bool = False) -> dict:
    p = cfgmod.tmh_dir(root) / "map.json"
    if p.exists() and not rebuild:
        return json.loads(p.read_text(encoding="utf-8"))
    m = build_map(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def where(root: Path, keywords: list[str], limit: int = 20) -> list[dict]:
    root = root.resolve()
    m = load_map(root)
    kws = [k for k in keywords if k.strip()]
    lower = [k.lower() for k in kws]
    score: dict[str, float] = defaultdict(float)
    why: dict[str, list[str]] = defaultdict(list)

    def bump(f: str, s: float, reason: str) -> None:
        score[f] += s
        if len(why[f]) < 6 and reason not in why[f]:
            why[f].append(reason)

    for e in m.get("endpoints", []):
        hay = (e["path"] + " " + e["handler"]).lower()
        for k in lower:
            if k in hay:
                bump(e["file"], 5, "入口 %s %s → %s (行 %s)" % (e["method"], e["path"], e["handler"], e.get("line", 0)))
    for name, defs in m.get("symbols", {}).items():
        for k in lower:
            if k in name.lower():
                for d in defs:
                    bump(d["file"], 4, "定义 %s %s (行 %s)" % (d["kind"], name, d["line"]))
    for table, files in m.get("tables", {}).items():
        for k in lower:
            if k == table.lower() or (len(k) >= 4 and k in table.lower()):
                for f in files:
                    bump(f, 3, "访问表 %s" % table)
    for da in m.get("data_access", []):
        for st in da.get("statements", []):
            for k in lower:
                if k in st["id"].lower():
                    bump(da["file"], 3, "SQL %s.%s (行 %s)" % (da["namespace"].rsplit(".", 1)[-1], st["id"], st["line"]))
    # Full-text pass: catches Chinese business words in comments, labels and messages.
    rxs = [re.compile(re.escape(k), re.I) for k in kws]
    for p in iter_files(root):
        if p.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        text = read_text(p)
        if not text:
            continue
        rp = rel(root, p)
        for k, rx in zip(kws, rxs):
            hits = [i for i, line in enumerate(text.splitlines(), 1) if rx.search(line)]
            if hits:
                bump(rp, min(len(hits), 10) * 0.5 + 1, "文本含“%s” 行 %s" % (k, ",".join(map(str, hits[:5]))))
    ranked = sorted(score.items(), key=lambda kv: -kv[1])[:limit]
    return [{"file": f, "score": round(s, 1), "why": why[f]} for f, s in ranked]


def _names_defined_in(m: dict, rp: str) -> set[str]:
    names = {n for n, defs in m.get("symbols", {}).items() for d in defs if d["file"] == rp}
    for da in m.get("data_access", []):
        if da["file"] == rp and da.get("namespace"):
            names.add(da["namespace"].rsplit(".", 1)[-1])
    if not names and "." in rp:
        names.add(rp.rsplit("/", 1)[-1].split(".")[0])
    return {n for n in names if len(n) >= 3}


def impact(root: Path, target: str, depth: int = 3, limit: int = 80) -> dict:
    """Transitive reverse-reference walk: table/class/file → users → their users …"""
    root = root.resolve()
    m = load_map(root)
    res: dict = {"target": target, "defined_in": [], "table_users": [], "referenced_by": [],
                 "entrypoints_in_referrers": [], "jobs_in_referrers": []}
    seeds: set[str] = set()
    tgt_path = root / target
    if tgt_path.is_file():
        rp = rel(root, tgt_path)
        res["defined_in"] = [rp]
        res["tables_used"] = sorted(t for t, fs in m.get("tables", {}).items() if rp in fs)
        seeds = _names_defined_in(m, rp)
    else:
        res["defined_in"] = [d["file"] for d in m.get("symbols", {}).get(target, [])]
        seeds = {target}
        up = target.upper()
        if up in m.get("tables", {}):
            res["table_users"] = m["tables"][up]
            for f in res["table_users"]:
                seeds |= _names_defined_in(m, f)
    texts = {}
    for p in iter_files(root):
        if p.suffix.lower() in SOURCE_SUFFIXES:
            t = read_text(p)
            if t:
                texts[rel(root, p)] = t
    reached: dict[str, dict] = {}
    known_files = set(res["defined_in"]) | set(res["table_users"])
    frontier, seen_names = set(seeds), set()
    for level in range(1, depth + 1):
        names = frontier - seen_names
        if not names:
            break
        seen_names |= names
        rx = re.compile(r"\b(%s)\b" % "|".join(re.escape(n) for n in sorted(names)))
        nxt: set[str] = set()
        for rp, text in texts.items():
            if rp in known_files or rp in reached:
                continue
            lines = [i for i, l in enumerate(text.splitlines(), 1) if rx.search(l)]
            if not lines:
                continue
            via = sorted(set(rx.findall(text)))[:4]
            reached[rp] = {"file": rp, "level": level, "via": via, "lines": lines[:8]}
            nxt |= _names_defined_in(m, rp)
        frontier = nxt
    res["referenced_by"] = sorted(reached.values(), key=lambda r: (r["level"], r["file"]))[:limit]
    files = set(reached) | known_files
    res["entrypoints_in_referrers"] = [e for e in m.get("endpoints", []) if e["file"] in files][:limit]
    res["jobs_in_referrers"] = [j for j in m.get("jobs", []) if j["file"] in files][:limit]
    res["listeners_in_referrers"] = [j for j in m.get("listeners", []) if j["file"] in files][:limit]
    return res
