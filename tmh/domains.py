"""Business domains: group flows, tables and code into the areas people talk about.

First pass is automatic: flows are joined when their entry classes share a
business key (package segment or class stem, e.g. `leave` from LeaveController)
or when they write the same table (ignoring hub tables such as logs that many
areas write). The result is saved to `.tmh/knowledge/domains.json` and is
*sticky*: later rebuilds keep every flow where it was, put new flows into the
domain their cluster mostly belongs to, and only create domains for clusters
that match nothing. People (or the agent) rename and regroup domains by editing
that file; titles and assignments there always win.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .config import tmh_dir

SHARED = "shared"


def domains_path(root: Path) -> Path:
    return tmh_dir(root) / "knowledge" / "domains.json"


def load(root: Path) -> dict:
    p = domains_path(root)
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            d.setdefault("domains", {})
            d.setdefault("assign", {})
            return d
        except ValueError:
            pass
    return {"_说明": "业务域划分。可以改 title（域名称）和 assign（业务流 → 域）；tmh 重建时保留这里的划分，只为新业务流分配域。",
            "domains": {}, "assign": {}}


def _slug(s: str) -> str:
    s = re.sub(r"[^\w一-鿿]+", "-", s).strip("-").lower()
    return s[:40] or "domain"


class _UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def cluster(flows: list[dict], nodes: dict) -> tuple[list[list[str]], dict]:
    """Automatic clusters of flow ids, plus each flow's business key."""
    uf = _UF()
    keys = {}
    for f in flows:
        fd = nodes.get("fn:" + f["handler"], {}).get("data", {})
        cls = fd.get("cls", "")
        bkey = fd.get("bkey") or (nodes.get(cls, {}).get("data", {}).get("bkey") if cls else None)  # Go package functions: their file
        keys[f["id"]] = bkey or f["handler"].split(".")[0].lower()
        uf.find(f["id"])
    by_key = defaultdict(list)
    for fid, k in keys.items():
        by_key[k].append(fid)
    for fids in by_key.values():
        for x in fids[1:]:
            uf.union(fids[0], x)
    # Groups that own no table, or have only background entries (jobs, listeners), join the
    # group that owns the table they write most. Groups with their own tables stay apart,
    # so shared tables such as approval logs do not glue unrelated areas together.
    for _ in range(3):
        gflows = defaultdict(list)
        for f in flows:
            gflows[uf.find(f["id"])].append(f)
        writes = defaultdict(Counter)  # table -> group -> writes
        for g, fl in gflows.items():
            for f in fl:
                for t, ops in f["crud"].items():
                    if set(ops) & set("CUD"):
                        writes[t][g] += 1
        gkey = {g: Counter(keys[f["id"]] for f in fl).most_common(1)[0][0] for g, fl in gflows.items()}
        owner = {}
        for t, c in writes.items():  # a table belongs to the group named after it (USERS ↔ user), else to its main writer
            words = set(t.lower().split("_"))
            named = [g for g in c if gkey[g] in words or gkey[g] + "s" in words or gkey[g] + "es" in words]
            owner[t] = max(named, key=lambda g: c[g]) if named else c.most_common(1)[0][0]
        changed = False
        for g, fl in gflows.items():
            owns = [t for t, o in owner.items() if o == g]
            weak = all(f["kind"] != "接口" for f in fl)
            if owns and not weak:
                continue
            mine = Counter()
            for f in fl:
                for t, ops in f["crud"].items():
                    if owner.get(t) not in (None, g):
                        mine[t] += 3 if set(ops) & set("CUD") else 1
            if mine:
                uf.union(owner[mine.most_common(1)[0][0]], g)
                changed = True
        if not changed:
            break
    groups = defaultdict(list)
    for f in flows:
        groups[uf.find(f["id"])].append(f["id"])
    return list(groups.values()), keys


def assign(root: Path, flows: list[dict], nodes: dict, common_pkg: list[str]) -> dict:
    state = load(root)
    doms, asg = state["domains"], state["assign"]
    live = {f["id"] for f in flows}
    for fid in list(asg):
        if fid not in live:
            del asg[fid]
    groups, keys = cluster(flows, nodes)
    for g in groups:
        votes = Counter(asg[f] for f in g if f in asg)
        if votes:
            target = votes.most_common(1)[0][0]
        else:
            key = Counter(keys[f] for f in g).most_common(1)[0][0]
            target = _slug(key)
            base, k = target, 2
            while target in doms:
                target = "%s-%d" % (base, k)
                k += 1
            doms[target] = {"title": key, "key": key, "auto": True}
        for f in g:
            asg.setdefault(f, target)
    for did in list(doms):
        if did not in set(asg.values()) and doms[did].get("auto"):
            del doms[did]
    fl_by = {f["id"]: f for f in flows}
    # tables follow the domain that writes them most (then reads)
    score = defaultdict(Counter)
    for fid, did in asg.items():
        for t, ops in fl_by[fid]["crud"].items():
            score[t][did] += 3 if set(ops) & set("CUD") else 1
    table_dom = {t: c.most_common(1)[0][0] for t, c in score.items()}
    # code follows the flows that reach it; code reached from several domains is shared
    code_dom = {}
    reach = defaultdict(set)
    for f in flows:
        did = asg.get(f["id"])
        for n in f["nodes"]:
            if n["layer"] != "table":
                reach["fn:" + n["key"]].add(did)
    for nid, ds in reach.items():
        code_dom[nid] = ds.pop() if len(ds) == 1 else SHARED
    cls_votes = defaultdict(Counter)
    for nid, did in code_dom.items():
        cls = nodes.get(nid, {}).get("data", {}).get("cls")
        if cls:
            cls_votes[cls][did] += 1
    for cls, c in cls_votes.items():
        code_dom[cls] = c.most_common(1)[0][0] if len(c) == 1 else SHARED
    out = {}
    for did, d in doms.items():
        out[did] = {"title": d.get("title") or did, "key": d.get("key", ""),
                    "flows": sorted(f for f, x in asg.items() if x == did),
                    "tables": sorted(t for t, x in table_dom.items() if x == did)}
    state["domains"], state["assign"] = doms, dict(sorted(asg.items()))
    p = domains_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"domains": out, "code_domain": code_dom}
