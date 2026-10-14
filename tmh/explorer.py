"""Project explorer: the report for real-size systems.

Static analysis supplies the facts (call chains, tables, states, rules, code
locations); the knowledge pages written by the agent supply the understanding
(business language, domain names, inferences). The explorer shows both, layered
the way people read a system: 业务全景 → 业务域 → 业务流 → 代码, with every
statement marked 代码核实 (static fact or cited file:line) or 模型推断 (【推断】
in a page) and the review status of each page.

Output is a folder that opens offline from disk:

  .tmh/report/index.html        app + overview data (domains, build analysis, search index)
  .tmh/report/data/d<N>.js      one file per domain, loaded on demand with <script>
                                (fetch() does not work on file://)
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import config as cfgmod

MAX_FLOW_NODES = 150
MAX_OPS = 60
INFER_RX = re.compile(r"【推断】|〔推断〕")


def _page(root: Path, pid: str, reg: dict) -> dict | None:
    from . import kb
    r = reg.get(pid)
    p = kb.page_path(root, pid)
    if not r or not p.exists():
        return None
    written = r.get("status") != kb.STATUS_NEW
    if not written:
        return None
    pg = kb.parse_page(p.read_text(encoding="utf-8"))
    body = pg["body"]
    if kb.PLACEHOLDER.match(re.sub(r"^##.*$|（[^）]*）", "", body, flags=re.M).strip() or ""):
        return None
    return {"status": "过期" if r.get("stale") else r.get("status", kb.STATUS_DRAFT), "title": pg["meta"].get("title", ""),
            "summary": r.get("summary") or pg["meta"].get("summary", ""), "body": body, "file": p.relative_to(root).as_posix(),
            "infer": len(INFER_RX.findall(body))}


def _compact_flow(f: dict) -> dict:
    nodes = f["nodes"]
    keep = nodes[:MAX_FLOW_NODES]
    idx = {n["id"]: i for i, n in enumerate(keep)}
    edges = [[idx[e["from"]], idx[e["to"]], e.get("op", "")] for e in f["edges"] if e["from"] in idx and e["to"] in idx]
    seen, ops = set(), []
    for o in f["data_ops"]:
        k = (o["table"], o["op"], o["via"])
        if k in seen:
            continue
        seen.add(k)
        ops.append([o["table"], o["op"], o["via"], (o.get("sql") or "")[:500], o.get("file", ""), o.get("line", 0)])
        if len(ops) >= MAX_OPS:
            break
    st, seen = [], set()
    for s in f["states"]:
        k = (s["table"], s["column"], tuple(s["from"]), s["to"])
        if k not in seen:
            seen.add(k)
            st.append([s["table"], s["column"], s["from"], s["to"], s["file"], s["line"]])
    rules, seen = [], set()
    for r in f["rules"]:
        k = (r["file"], r["line"])
        if k not in seen:
            seen.add(k)
            rules.append([r["condition"][:200], r.get("message") or r.get("exception") or "", r["file"], r["line"], r.get("method", "")])
    return {"id": f["id"], "name": f["name"], "kind": f["kind"], "trigger": f["trigger"], "handler": f["handler"], "file": f["file"], "line": f["line"],
            "crud": f["crud"], "root": idx.get(f.get("root"), 0),
            "n": [[n["label"], "dispatch" if n.get("dispatch") else n["layer"], n.get("file", ""), n.get("line", 0), (n.get("comment") or "")[:120]] for n in keep],
            "more": max(0, len(nodes) - len(keep)), "e": edges, "ops": ops, "st": st[:40], "rules": rules[:60],
            "tx": [[t["method"], t["file"], t["line"]] for t in f["transactions"]][:10],
            "fx": [[s["kind"], s.get("method", ""), s["file"], s["line"], s.get("code", "")] for s in f["side_effects"]][:20],
            "un": [[u["call"], u.get("why", ""), u.get("file", ""), u.get("line", 0)] for u in f["unresolved"]][:20]}


def build(root: Path, data: dict) -> dict:
    """Overview + per-domain payloads from the graph, flows, build facts and knowledge pages."""
    from . import kb
    from .graph import Graph
    root = root.resolve()
    cfg = cfgmod.load(root)
    flows = data["flows"]
    by_id = {f["id"]: f for f in flows}
    reg = kb.load_registry(root)
    try:
        g = Graph(root)
    except FileNotFoundError:
        g = None
    bpath = cfgmod.tmh_dir(root) / "cache" / "build.json"
    if bpath.exists():
        build_facts = json.loads(bpath.read_text(encoding="utf-8"))
    else:
        build_facts = kb.write_build_facts(root, g, flows)

    # domains: graph assignment, falling back to one bucket
    dom_flows: dict[str, list] = defaultdict(list)
    dom_title, tbl_dom, tbl_entity = {}, {}, {}
    if g is not None:
        for n in g.nodes("dom"):
            dom_title[n["id"][4:]] = n["label"]
        for n in g.nodes("flow"):
            if n["id"][5:] in by_id:
                dom_flows[n["domain"] or "_"].append(n["id"][5:])
        for n in g.nodes("tbl"):
            if n["domain"]:
                tbl_dom[n["name"]] = n["domain"]
            if n["data"].get("entity"):
                tbl_entity[n["name"]] = n["data"]["entity"]
    else:
        dom_flows["_"] = list(by_id)
    if dom_flows.get("_"):
        dom_title["_"] = "未划分"

    sms_by_table = defaultdict(list)
    for sm in data["state_machines"]:
        sms_by_table[sm["table"]].append(sm)

    domains, payloads, search = [], {}, []
    order = sorted(dom_flows, key=lambda d: (d == "_", -len(dom_flows[d])))
    for i, did in enumerate(order):
        fids = dom_flows[did]
        page = _page(root, "dom:" + did, reg) if did != "_" else None
        title = (page or {}).get("title") or dom_title.get(did, did)
        writes, reads = Counter(), Counter()
        rel = Counter()
        kinds = Counter()
        fl_out = []
        for fid in fids:
            f = by_id[fid]
            kinds[f["kind"]] += 1
            for t, ops in f["crud"].items():
                (writes if set(ops) & set("CUDP") else reads)[t] += 1
                od = tbl_dom.get(t)
                if od and od != did:
                    rel[od] += 1
            cf = _compact_flow(f)
            fp = _page(root, "flow:" + fid, reg)
            if fp:
                cf["page"] = fp
            fl_out.append(cf)
            search.append(["f", fid, i, (fp or {}).get("title") or f["name"] or "", f["trigger"], f["handler"]])
        own = [t for t, d in tbl_dom.items() if d == did]
        tables = []
        for t in sorted(set(own) | set(writes), key=lambda t: (-(writes[t] + reads[t]), t)):
            tp = _page(root, "tbl:" + t, reg)
            row = {"name": t, "entity": tbl_entity.get(t, ""), "owner": tbl_dom.get(t, ""), "w": writes[t], "r": reads[t],
                   "sm": [sm["column"] for sm in sms_by_table.get(t, [])]}
            if tp:
                row["page"] = tp
            tables.append(row)
            search.append(["t", t, i, (tp or {}).get("title") or tbl_entity.get(t, ""), "", ""])
        sms = []
        for t in [x["name"] for x in tables]:
            for sm in sms_by_table.get(t, []):
                trs = [[x["from"], x["to"], x["flow"], x["flow_name"], x["file"], x["line"]] for x in sm["transitions"][:300]]
                sms.append({"table": t, "column": sm["column"], "states": sm["states"], "tr": trs, "total": len(sm["transitions"])})
        n_rules = sum(len(by_id[f]["rules"]) for f in fids)
        n_infer = sum(x.get("page", {}).get("infer", 0) for x in fl_out) + (page or {}).get("infer", 0)
        n_pages = sum(1 for x in fl_out if x.get("page"))
        domains.append({"id": did, "i": i, "title": title, "key": did, "summary": (page or {}).get("summary", ""),
                        "status": (page or {}).get("status", ""), "flows": len(fids), "kinds": dict(kinds),
                        "tables": [t for t, _ in (writes + reads).most_common(6)], "writes": len(writes), "sms": len(sms),
                        "rules": n_rules, "pages": n_pages, "infer": n_infer, "rel": [[d, c] for d, c in rel.most_common(8)]})
        search.append(["d", did, i, title, did, ""])
        payloads[i] = {"id": did, "title": title, "page": page, "flows": fl_out, "tables": tables, "sms": sms}

    idx_page = _page(root, "index", reg)
    free = {}
    k = kb.kdir(root)
    for name in ("glossary.md", "pitfalls.md", "open-questions.md", "decisions.md"):
        p = k / name
        if p.exists():
            t = p.read_text(encoding="utf-8")
            if t.strip() != kb.FREE_PAGES.get(name, "").strip():
                free[name] = t
    cov = kb.coverage(reg) if reg else {}
    n_tables = len({t for f in flows for t in f["crud"]})
    overview = {
        "project": cfg.get("project", {}).get("name") or root.name, "generated": time.strftime("%Y-%m-%d %H:%M"),
        "stats": {"flows": len(flows), "with_tables": sum(1 for f in flows if f["crud"]), "tables": n_tables, "sms": len(data["state_machines"]),
                  "rules": sum(len(f["rules"]) for f in flows), "domains": len(domains), "unresolved": sum(len(f["unresolved"]) for f in flows)},
        "coverage": cov, "build": build_facts, "index": idx_page, "free": free, "domains": domains, "search": search,
    }
    return {"overview": overview, "payloads": payloads}


def write(root: Path, data: dict) -> Path:
    from .explorer_ui import APP_CSS, APP_JS
    res = build(root, data)
    d = cfgmod.tmh_dir(root) / "report"
    dd = d / "data"
    dd.mkdir(parents=True, exist_ok=True)
    for i, pl in res["payloads"].items():
        (dd / ("d%d.js" % i)).write_text("TMH.loaded(%d,%s);\n" % (i, _js(pl)), encoding="utf-8")
    ov = res["overview"]
    html = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>%s · 业务全景</title><style>%s</style></head><body><div id=app></div>"
            "<script>window.TMH_OVERVIEW=%s;</script><script>%s</script></body></html>") % (
        _esc(ov["project"]), APP_CSS, _js(ov), APP_JS)
    p = d / "index.html"
    p.write_text(html, encoding="utf-8")
    return p


def _js(o) -> str:
    # JSON is valid JS; escape "</" so a string containing </script> cannot end the tag
    return json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
