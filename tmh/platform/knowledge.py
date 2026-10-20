"""知识层: what a project is, for every layer above it.

Business domains, flows, tables, entry points and the code evidence behind them, read from the project's graph
(graph.db) and knowledge-base pages (.tmh/knowledge). The coding line (orchestra.py) asks it which flows a task
touches; the apps show it as the atlas, the knowledge base and the architecture map; after a run it queues the pages
that run made stale. It does not know about tickets except to show which open ones sit on a flow.
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from pathlib import Path

from .errors import ApiError
from .store import now


class Knowledge:
    def __init__(self, store, runner):
        self.store, self.runner = store, runner
        self._ov = {}

    def root(self, p: dict) -> Path:
        from .project_library import require_development
        try:
            require_development(self.store, p)
        except ValueError as exc:
            raise ApiError(409, str(exc)) from exc
        return Path(p["root"])

    def forget(self, project_id: int) -> None:
        """Drop the cached overview after the knowledge base changed (a survey batch finished, pages were written)."""
        self._ov.pop(project_id, None)

    def kb_overview(self, p: dict) -> dict:
        """Knowledge-base numbers for one project, cached on graph.db's mtime."""
        from .project_library import profile
        if profile(self.store, p)['workflow'] == 'reference':
            return {'built': False, 'workflow': 'reference', 'notice': '固定知识版本请在“知识与引用”查看'}
        from ..graph import Graph, graph_path
        root = self.root(p)
        gp = graph_path(root)
        if not gp.exists():
            return {"built": False}
        mt = gp.stat().st_mtime
        c = self._ov.get(p["id"])
        if c and c[0] == mt:
            return c[1]
        from .. import kb
        g = Graph(root)
        flows = g.nodes("flow")
        tables = g.nodes("tbl")
        doms = {}
        for f in flows:
            d = f.get("domain") or "（未划分）"
            doms[d] = doms.get(d, 0) + 1
        reg = kb.load_registry(root)
        dom_title = {}
        for n in g.nodes("dom"):
            dom_title[n["name"]] = n["label"] or n["name"]
            dom_title[n["id"][4:]] = n["label"] or n["name"]
        ov = {"built": True, "flows": len(flows), "tables": len(tables),
              "flows_with_tables": sum(1 for f in flows if (f["data"].get("crud") or {})),
              "domains": sorted(([k, dom_title.get(k, k), v] for k, v in doms.items()), key=lambda x: -x[2]),
              "coverage": kb.coverage(reg), "report": (root / ".tmh" / "report" / "index.html").exists(),
              "built_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(mt))}
        self._ov[p["id"]] = (mt, ov)
        return ov

    def related(self, p: dict, text: str, limit: int = 8) -> dict:
        """Structured 'what in the business does this touch': flows, tables, pages, code — for chips in the UI."""
        from ..graph import Graph, graph_path
        root = self.root(p)
        if not graph_path(root).exists() or not text.strip():
            return {"flows": [], "tables": [], "pages": [], "code": []}
        from ..context import search
        from .. import kb
        g = Graph(root)
        reg = kb.load_registry(root)
        hits = search(root, text, limit=60)
        out = {"flows": [], "tables": [], "pages": [], "code": []}
        seen = set()
        for s, d in hits:
            nid = d["id"]
            if nid in seen:
                continue
            seen.add(nid)
            if nid.startswith("flow:") and len(out["flows"]) < limit:
                n = g.node(nid)
                if n:
                    dd = n["data"]
                    out["flows"].append({"id": nid, "name": n["name"], "trigger": dd.get("trigger", ""), "handler": dd.get("handler", ""),
                                         "file": n["file"], "line": n["line"], "domain": n.get("domain", ""),
                                         "tables": list((dd.get("crud") or {}).items())[:8], "score": round(s, 1),
                                         "page": reg.get(nid, {}).get("status", "")})
            elif nid.startswith("tbl:") and len(out["tables"]) < limit:
                n = g.node(nid)
                if n:
                    out["tables"].append({"id": nid, "name": n["name"], "entity": n["data"].get("entity", ""),
                                          "users": len(g.inn(nid, "uses"))})
            elif d["type"] == "page" and len(out["pages"]) < limit:
                r = reg.get(nid, {})
                out["pages"].append({"id": nid, "title": r.get("title") or nid, "status": "过期" if r.get("stale") else r.get("status", kb.STATUS_NEW),
                                     "summary": r.get("summary", "")})
            elif nid.split(":")[0] in ("fn", "cls") and len(out["code"]) < limit:
                n = g.node(nid)
                if n and n["file"]:
                    out["code"].append({"id": nid, "label": n["label"], "file": n["file"], "line": n["line"]})
        return out

    def kb_followup(self, p: dict, t: dict, run: dict, n: int, author: str) -> list:
        """After a ticket analysis: write the knowledge pages of the business flows it touched that nobody wrote yet.

        The flows are the ones the analysis names (flow:... ids) plus the ones linked to the ticket, so the
        knowledge base grows along real work instead of being written all at once."""
        from .. import kb
        root = self.root(p)
        reg = kb.load_registry(root)
        ids = list((t.get("links") or {}).get("flows") or []) + [x.rstrip(".") for x in re.findall(r"flow:[A-Za-z0-9_.\-]+", run.get("result") or "")]
        todo = []
        for fid in ids:
            r = reg.get(fid)
            if r is None or r.get("orphan") or fid in todo:
                continue
            if r.get("stale") or r.get("status", kb.STATUS_NEW) == kb.STATUS_NEW:
                todo.append(fid)
        todo = todo[:max(0, n)]
        if not todo:
            return []
        kb.add_pages(root, todo, "工单 " + t["key"])
        self.store.event(t["id"], run["agent"], "kb", "补写这次分析涉及的知识页：" + "、".join(todo),
                         {"pages": todo, "run": run["id"]})

        def work():
            for pid in todo:
                r = self.runner.start(p, None, run["agent"], "kb", author, pid, batch="after-%d" % run["id"], model=None)
                while self.store.run(r["id"])["status"] in ("queued", "running"):
                    time.sleep(2)
                reg2 = kb.load_registry(root).get(pid, {})
                ok = reg2.get("status") not in (None, kb.STATUS_NEW) and not reg2.get("stale")
                self.store.event(t["id"], run["agent"], "kb", "知识页%s：%s" % ("写成" if ok else "没写成", reg2.get("title") or pid),
                                 {"page": pid, "run": r["id"]})
                self._ov.pop(p["id"], None)
                if not ok and self.store.run(r["id"])["status"] == "failed":
                    break
        threading.Thread(target=work, daemon=True).start()
        return todo

    def flow_detail(self, p: dict, fid: str) -> dict:
        from ..graph import Graph
        g = Graph(self.root(p))
        n = g.node(fid if fid.startswith("flow:") else "flow:" + fid)
        if not n:
            raise ApiError(404, "没有这条业务流")
        steps = []
        for e in g.out(n["id"], "step")[:80]:
            m = g.node(e["dst"])
            if m:
                steps.append({"label": m["label"], "file": m["file"], "line": m["line"]})
        tickets = [t for t in self.store.tickets(project_id=p["id"], limit=2000)
                   if n["id"] in ((t.get("links") or {}).get("flows") or [])]
        return {"id": n["id"], "name": n["name"], "file": n["file"], "line": n["line"], "domain": n.get("domain", ""),
                "data": {k: n["data"].get(k) for k in ("trigger", "handler", "crud", "states", "rules") if k in n["data"]},
                "steps": steps, "tickets": [{"key": t["key"], "title": t["title"], "status": t["status"]} for t in tickets]}

    def kb_pages(self, p: dict, status: str = "", q: str = "", kind: str = "") -> list:
        from .. import kb
        reg = kb.load_registry(self.root(p))
        out = []
        for pid, r in reg.items():
            if r.get("orphan"):
                continue
            st = "过期" if r.get("stale") else r.get("status", kb.STATUS_NEW)
            if not r.get("scope") and st == kb.STATUS_NEW:
                st = "仅事实"
            k = kb.page_kind(pid)
            if (status and st != status) or (kind and k != kind):
                continue
            if q and q.lower() not in (pid + (r.get("title") or "") + (r.get("summary") or "")).lower():
                continue
            out.append({"id": pid, "kind": k, "title": r.get("title") or pid, "status": st, "summary": r.get("summary", ""),
                        "confirmed_by": r.get("confirmed_by", ""), "confirmed_at": r.get("confirmed_at", ""), "stale": bool(r.get("stale"))})
        order = {"过期": 0, "待确认": 1, "已确认": 2, "未分析": 3, "仅事实": 4}
        out.sort(key=lambda x: (order.get(x["status"], 9), x["kind"] != "index", x["kind"], x["id"]))
        return out[:600]

    @staticmethod
    def _kb_status(r: dict) -> str:
        from .. import kb
        st = "需更新" if r.get("stale") else r.get("status", kb.STATUS_NEW)
        return "仅事实" if not r.get("scope") and st == kb.STATUS_NEW else st

    def kb_tree(self, p: dict) -> dict:
        """The reading directory: business domains with their flows; pages with a written explanation first.

        Unwritten pages stay listed (marked 未分析 / 仅事实) so nothing becomes unfindable."""
        from .. import kb
        from ..graph import Graph, graph_path
        root = self.root(p)
        if not graph_path(root).exists():
            return {"built": False, "domains": []}
        g = Graph(root)
        reg = kb.load_registry(root)
        rank = {"已确认": 0, "待确认": 1, "需更新": 2, "未分析": 3, "仅事实": 4}
        doms = {}
        for n in g.nodes("dom"):
            r = reg.get(n["id"], {})
            doms[n["data"].get("key") or n["name"]] = {"id": n["id"], "title": r.get("title") or n["label"] or n["name"], "status": self._kb_status(r) if r else "仅事实",
                                                       "summary": r.get("summary", ""), "flows": [], "tables": set()}
        other = {"id": "", "title": "未划分业务域", "status": "", "summary": "", "flows": [], "tables": set()}
        for f in g.nodes("flow"):
            r = reg.get(f["id"], {})
            d = doms.get(f.get("domain") or "", other)
            d["flows"].append({"id": f["id"], "title": r.get("title") or f["name"], "status": self._kb_status(r) if r else "仅事实",
                               "summary": r.get("summary", ""), "entry": f["data"].get("trigger", "")})
            d["tables"].update((f["data"].get("crud") or {}).keys())
        out = []
        for d in list(doms.values()) + ([other] if other["flows"] else []):
            d["flows"].sort(key=lambda x: (rank.get(x["status"], 9), x["title"]))
            d["tables"] = len(d["tables"])
            d["written"] = sum(1 for x in d["flows"] if x["status"] in ("已确认", "待确认"))
            out.append(d)
        out.sort(key=lambda d: (rank.get(d["status"], 9), -d["written"], -len(d["flows"])))
        ix = reg.get("index")
        return {"built": True, "domains": out, "index": ix and {"id": "index", "title": ix.get("title") or "系统总览", "status": self._kb_status(ix),
                                                                 "summary": ix.get("summary", "")}}

    def arch(self, p: dict) -> dict:
        """System overview from tool-parsed facts only: entries → business domains → tables and external calls.

        Deployment (servers, proxies, caches) is not in the code facts, so it is not drawn as if it were."""
        from .. import kb
        from ..graph import Graph, graph_path
        root = self.root(p)
        if not graph_path(root).exists():
            return {"built": False}
        g = Graph(root)
        reg = kb.load_registry(root)
        flows = g.nodes("flow")
        entries = Counter(f["data"].get("entry_kind") or "其他入口" for f in flows)
        uses = Counter()
        for f in flows:
            for t in (f["data"].get("crud") or {}):
                uses[t] += 1
        tree = self.kb_tree(p)["domains"]
        doms = [{"id": d["id"], "title": d["title"], "flows": len(d["flows"]), "tables": d["tables"], "status": d["status"],
                 "summary": d["summary"], "written": d["written"]} for d in tree]
        doms.sort(key=lambda d: -d["flows"])
        ext = [{"id": n["id"], "title": n["label"] or n["name"], "users": len(g.inn(n["id"]))} for n in g.nodes("ext")]
        unresolved = sum(int(f["data"].get("unresolved") or 0) for f in flows)
        ix = reg.get("index", {})
        return {"built": True, "entries": entries.most_common(), "flows": len(flows), "domains": doms,
                "tables": len(g.nodes("tbl")), "top_tables": uses.most_common(8), "ext": sorted(ext, key=lambda e: -e["users"]),
                "classes": len(g.nodes("cls")), "methods": len(g.nodes("fn")), "unresolved": unresolved,
                "overview": ix.get("summary", ""), "overview_status": self._kb_status(ix) if ix else "",
                "report": (root / ".tmh" / "report" / "index.html").exists(), "built_at": self.kb_overview(p).get("built_at", "")}

    # ------------------------------------------------------------ project atlas
    # The knowledge base drawn as one picture: business domains, the tables they share, and inside each domain its
    # flows; a flow opens as its chain entry → methods → tables. Facts come from the tool-parsed graph, titles and
    # summaries from the written pages, and open tickets sit on the flows they touch.
    def _open_tickets_by_flow(self, p: dict) -> dict:
        out = {}
        for t in self.store.tickets(project_id=p["id"], limit=5000):
            if t["status"] == "closed":
                continue
            for f in ((t.get("links") or {}).get("flows") or []):
                out.setdefault(f, []).append({"key": t["key"], "title": t["title"], "status": t["status"]})
        return out

    def atlas(self, p: dict) -> dict:
        from .. import kb
        from ..graph import Graph, graph_path
        root = self.root(p)
        if not graph_path(root).exists():
            return {"built": False}
        g = Graph(root)
        reg = kb.load_registry(root)
        tk = self._open_tickets_by_flow(p)
        doms, by_key = [], {}
        for n in g.nodes("dom"):
            r = reg.get(n["id"], {})
            d = {"id": n["id"], "title": r.get("title") or n["label"] or n["name"], "summary": r.get("summary", ""),
                 "status": self._kb_status(r) if r else "仅事实", "flows": 0, "tables": {}, "tickets": 0, "written": 0}
            doms.append(d)
            by_key[n["data"].get("key") or n["name"]] = d
        other = {"id": "dom:_", "title": "未划分业务域", "summary": "", "status": "", "flows": 0, "tables": {}, "tickets": 0, "written": 0}
        flows = []
        for f in g.nodes("flow"):
            r = reg.get(f["id"], {})
            d = by_key.get(f.get("domain") or "", other)
            st = self._kb_status(r) if r else "仅事实"
            crud = f["data"].get("crud") or {}
            ts = tk.get(f["id"], [])
            d["flows"] += 1
            d["tickets"] += len(ts)
            d["written"] += st in ("已确认", "待确认")
            for t, ops in crud.items():
                d["tables"][t] = d["tables"].get(t, "") + ops
            flows.append({"id": f["id"], "title": r.get("title") or f["name"], "domain": d["id"], "entry": f["data"].get("trigger", ""),
                          "kind": f["data"].get("entry_kind", ""), "status": st, "summary": r.get("summary", ""), "crud": crud,
                          "steps": f["data"].get("steps") if isinstance(f["data"].get("steps"), int) else len(f["data"].get("steps") or []),
                          "unresolved": f["data"].get("unresolved") or 0, "file": f["file"], "line": f["line"], "tickets": ts})
        if other["flows"]:
            doms.append(other)
        tables = {}
        for d in doms:
            for t, ops in d["tables"].items():
                x = tables.setdefault(t, {"id": "tbl:" + t, "name": t, "domains": {}, "flows": 0, "write": False})
                x["domains"][d["id"]] = ops
                x["write"] = x["write"] or any(c in ops for c in "CUDP")
        for f in flows:
            for t in f["crud"]:
                if t in tables:
                    tables[t]["flows"] += 1
        for t in tables.values():
            n = g.node(t["id"])
            r = reg.get(t["id"], {})
            t["label"] = (r.get("title") or (n and n["label"]) or "") if (r.get("title") or (n and n["label"] != t["name"])) else ""
            t["summary"] = r.get("summary", "")
        # two domains are linked when they touch the same table; the shared tables say why
        links = {}
        for t in tables.values():
            ds = sorted(t["domains"])
            for i in range(len(ds)):
                for j in range(i + 1, len(ds)):
                    links.setdefault((ds[i], ds[j]), []).append(t["name"])
        for d in doms:
            d["tables"] = len(d["tables"])
        ix = reg.get("index", {})
        return {"built": True, "project": {"key": p["key"], "name": p["name"], "summary": ix.get("summary", "")},
                "domains": doms, "flows": flows, "tables": list(tables.values()),
                "links": [{"a": a, "b": b, "tables": ts[:12], "n": len(ts)} for (a, b), ts in links.items()],
                "stats": {"domains": len(doms), "flows": len(flows), "tables": len(tables), "methods": len(g.nodes("fn")),
                          "tickets": sum(len(v) for v in tk.values()), "written": sum(d["written"] for d in doms)},
                "built_at": self.kb_overview(p).get("built_at", "")}

    LAYER = {"entry": "入口", "controller": "入口", "service": "业务", "biz": "业务", "dao": "数据", "mapper": "数据", "repository": "数据"}

    def atlas_flow(self, p: dict, fid: str) -> dict:
        """One flow as a chain: entry, the methods it runs (with layer, file:line and what each reads or writes), tables, side effects."""
        from .. import kb
        from ..graph import Graph
        g = Graph(self.root(p))
        n = g.node(fid if fid.startswith("flow:") else "flow:" + fid)
        if not n:
            raise ApiError(404, "没有这条业务流")
        reg = kb.load_registry(self.root(p))
        r = reg.get(n["id"], {})
        steps, seen = [], set()
        for e in g.out(n["id"], "step")[:60]:
            m = g.node(e["dst"])
            if not m or m["id"] in seen:
                continue
            seen.add(m["id"])
            lay = (m["data"].get("layer") or "").lower()
            io = [{"table": x["dst"][4:], "op": x["op"] or ("W" if x["kind"] == "writes" else "R")} for x in g.out(m["id"]) if x["kind"] in ("reads", "writes")]
            fx = [(g.node(x["dst"]) or {}).get("label") or x["dst"][4:] for x in g.out(m["id"], "effect")]
            calls = [x["dst"] for x in g.out(m["id"], "calls")]
            steps.append({"id": m["id"], "label": m["label"] or m["name"], "name": m["name"], "layer": self.LAYER.get(lay, "其他"),
                          "comment": m["data"].get("comment", ""), "file": m["file"], "line": m["line"], "end": m.get("end_line") or m["line"],
                          "io": io, "effects": fx, "calls": calls})
        d = n["data"]
        return {"id": n["id"], "title": r.get("title") or n["name"], "summary": r.get("summary", ""), "status": self._kb_status(r) if r else "仅事实",
                "entry": d.get("trigger", ""), "kind": d.get("entry_kind", ""), "handler": d.get("handler", ""), "crud": d.get("crud") or {},
                "file": n["file"], "line": n["line"], "steps": steps, "unresolved": d.get("unresolved") or 0,
                "tickets": self._open_tickets_by_flow(p).get(n["id"], [])}

    def domain_detail(self, p: dict, did: str) -> dict:
        """One business domain for 架构与依据: each flow's entry, handler, file:line, tables and the boundaries tools could not resolve."""
        from .. import kb
        from ..graph import Graph
        root = self.root(p)
        g = Graph(root)
        reg = kb.load_registry(root)
        n = g.node(did)
        if not n:
            raise ApiError(404, "没有这个业务域：%s" % did)
        key = n["data"].get("key") or n["name"]
        r = reg.get(did, {})
        fl = []
        for f in g.nodes("flow"):
            if (f.get("domain") or "") != key:
                continue
            d = f["data"]
            fr = reg.get(f["id"], {})
            fl.append({"id": f["id"], "title": fr.get("title") or f["name"], "status": self._kb_status(fr) if fr else "仅事实",
                       "entry": d.get("trigger", ""), "entry_kind": d.get("entry_kind", ""), "handler": d.get("handler", ""),
                       "file": f["file"], "line": f["line"], "crud": d.get("crud") or {}, "steps": d.get("steps") if isinstance(d.get("steps"), int) else len(d.get("steps") or []),
                       "states": d.get("states") or 0, "unresolved": d.get("unresolved") or 0, "summary": fr.get("summary", "")})
        fl.sort(key=lambda x: x["entry"])
        return {"id": did, "title": r.get("title") or n["label"] or n["name"], "status": self._kb_status(r) if r else "仅事实",
                "summary": r.get("summary", ""), "flows": fl}

    def kb_page(self, p: dict, pid: str) -> dict:
        from .. import kb
        path = kb.page_path(self.root(p), pid)
        if not path.exists():
            raise ApiError(404, "知识页不存在：%s" % pid)
        r = kb.load_registry(self.root(p)).get(pid, {})
        return {"id": pid, "text": path.read_text(encoding="utf-8"), "path": path.relative_to(self.root(p)).as_posix(),
                "status": self._kb_status(r) if r else "", "kind": kb.page_kind(pid), "confirmed_by": r.get("confirmed_by", ""),
                "confirmed_at": r.get("confirmed_at", ""), "confirm_note": r.get("confirm_note", "")}
