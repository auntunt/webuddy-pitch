"""Project knowledge graph: the deterministic, incrementally rebuilt fact layer.

`build()` turns the project map, code index and traced business flows into one
graph stored in `.tmh/cache/graph.db` (SQLite):

  nodes  mod: module · file: source file · cls: class · fn: method · ep: entry
         (URL / job / listener) · tbl: table or procedure · flow: business flow ·
         dom: business domain · sm: state machine (table.column) · ext: side effect
  edges  contains · handles (ep→fn) · calls (fn→fn) · reads/writes (fn→tbl, op C/R/U/D/P)
         · effect (fn→ext) · step (flow→fn) · uses (flow→tbl) · in (flow/tbl→dom)
         · transition (flow→sm) · depends (mod→mod)

Every node carries a content hash (method body, class members, table DDL and SQL
touching it, …). Wiki pages record the hashes of the nodes they describe, so a
code change marks exactly the affected pages stale (see kb.py). Parsing is cached
per file (parsecache.py), so a rebuild after a small change only re-parses the
changed files; the graph itself is cheap to recompute in memory.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from . import domains as dommod
from .config import tmh_dir
from .fsutil import iter_files, open_db, read_text, rel, replace_file

LAYER_WORDS = {"controller", "controllers", "service", "services", "impl", "web", "action", "actions", "dao", "daos", "mapper",
               "mappers", "repository", "repositories", "api", "job", "jobs", "task", "tasks", "entity", "entities", "model",
               "models", "domain", "dto", "vo", "po", "bo", "util", "utils", "common", "core", "config", "handler", "handlers",
               "listener", "listeners", "data", "biz", "manager", "facade", "provider", "rest", "endpoint", "servlet", "main",
               "java", "src", "com", "cn", "org", "net", "www", "app", "data"}


def _h(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(json.dumps(p, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _norm_code(s: str) -> str:
    return " ".join((s or "").split())


def graph_path(root: Path) -> Path:
    return tmh_dir(root) / "cache" / "graph.db"


# ---- modules -----------------------------------------------------------
BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")


def detect_modules(root: Path, files: list[str]) -> dict:
    """Map module dir ('' = repo root) -> info, from build files (Maven/Gradle module, .csproj)."""
    mods = {}
    for f in files:
        name = f.rsplit("/", 1)[-1]
        d = f.rsplit("/", 1)[0] if "/" in f else ""
        if name == "go.mod":
            mods[d] = {"dir": d, "build": f, "name": d.rsplit("/", 1)[-1] or root.name}
        elif name in BUILD_FILES or name.endswith((".csproj", ".vbproj")):
            mods[d] = {"dir": d, "build": f, "name": (name[:-7] if name.endswith((".csproj", ".vbproj")) else (d.rsplit("/", 1)[-1] or root.name))}
    if not mods:
        mods[""] = {"dir": "", "build": "", "name": root.name}
    return mods


def module_of(path: str, mod_dirs: list[str]) -> str:
    best = None
    for d in mod_dirs:
        if d == "" or path == d or path.startswith(d + "/"):
            if best is None or len(d) > len(best):
                best = d
    return best if best is not None else ""


def git_churn(root: Path, limit: int = 2000) -> Counter:
    try:
        out = subprocess.run(["git", "log", "-n", str(limit), "--name-only", "--format="], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return Counter()
    return Counter(l.strip() for l in out.stdout.splitlines() if l.strip())


def business_key(cls_name: str, fqn: str, common_prefix: list[str]) -> str:
    segs = [s for s in fqn.split(".")[:-1]]
    segs = segs[len(common_prefix):] if segs[:len(common_prefix)] == common_prefix else segs
    segs = [s for s in segs if s.lower() not in LAYER_WORDS]
    if segs:
        return segs[-1].lower()
    base = re.sub(r"(Controller|Service|ServiceImpl|Impl|Action|Servlet|Job|Task|Listener|Handler|Facade|Api|Resource|Endpoint|Manager|Biz)$", "", cls_name)
    return base.lower() or cls_name.lower()


# ---- build ---------------------------------------------------------------
def build(root: Path, use_cache: bool = True) -> dict:
    from . import flow as flowmod, mapper, codeindex
    from .parsecache import ParseCache
    root = root.resolve()
    pc = ParseCache(root) if use_cache else None
    m = mapper.build_map(root, pc)
    idx = codeindex.build_index(root, pc)
    stats = {"parsed": pc.misses if pc else -1, "cached": pc.hits if pc else 0}
    if pc:
        pc.close()
    fb = flowmod.FlowBuilder(root, m, idx)
    fdata = flowmod.build_flows(root, builder=fb)
    flows = fdata["flows"]

    files = [rel(root, p) for p in iter_files(root)]
    mods = detect_modules(root, files)
    mod_dirs = list(mods)
    churn = git_churn(root)

    nodes: dict[str, dict] = {}
    edges: list[tuple] = []

    def node(nid, kind, name, label="", file="", line=0, end=0, h="", **data):
        n = nodes.get(nid)
        if n is None:
            n = nodes[nid] = {"id": nid, "kind": kind, "name": name, "label": label or name, "file": file, "line": line, "end": end or line,
                              "domain": "", "module": "", "hash": h, "data": {}}
        n["data"].update({k: v for k, v in data.items() if v not in (None, "", [], {})})
        if h:
            n["hash"] = h
        return n

    def edge(src, dst, kind, op="", file="", line=0):
        edges.append((src, dst, kind, op, file, line))

    # modules and files
    line_count = {}
    for d, info in mods.items():
        node("mod:" + (d or "."), "mod", info["name"], info["name"], info["build"], 0)
    src_suffix = (".go", ".java", ".cs", ".xml", ".jsp", ".aspx", ".cshtml", ".sql", ".vb", ".js", ".vue", ".ts", ".properties", ".yml", ".yaml", ".config", ".py")
    for f in files:
        if not f.endswith(src_suffix):
            continue
        md = module_of(f, mod_dirs)
        n = node("file:" + f, "file", f.rsplit("/", 1)[-1], f, f, 1)
        n["module"] = md or "."
        if f.endswith(".py"):
            diagnostics = [d for d in idx.get("diagnostics", []) if d["file"] == f]
            n["data"].update(analysis_status="unknown" if diagnostics else "parsed", diagnostics=diagnostics,
                              analysis_scope="Python AST 静态索引；不执行项目代码")
        is_test = bool(re.search(r"(^|/)(src/test|[^/]*\.Tests?|test|tests)/|Tests?\.(java|cs)$|_test\.go$|(^|/)(test_[^/]+|[^/]+_test)\.py$", f))
        n["data"].update({"churn": churn.get(f, 0), "test": is_test} if churn.get(f) or is_test else {})
        edge("mod:" + (md or "."), "file:" + f, "contains")

    # classes and methods
    common = _common_package([c["fqn"] for cs in idx["classes"].values() for c in cs])
    flow_keys = set()
    for cname, cs in idx["classes"].items():
        for c in cs:
            cid = "cls:" + c["fqn"]
            members = sorted(c["methods"]) + sorted(c["fields"])
            layer = fb._layer(c)
            node(cid, "cls", c["name"], c["fqn"], c["file"], c["line"], h=_h(members, c["bases"], c["annos"]), layer=layer, kind_=c["kind"],
                 bases=c["bases"], comment=c.get("comment", ""), bkey=c.get("bkey") or business_key(c["name"], c["fqn"], common))
            edge("file:" + c["file"], cid, "contains")
            for b in c["bases"]:
                for bc in idx["classes"].get(b, []):
                    edge(cid, "cls:" + bc["fqn"], "extends")
            for mname, ms in c["methods"].items():
                mm = next((x for x in ms if "body" in x), ms[0])
                fid = "fn:%s.%s" % (c["name"], mname)
                body_lines = (mm.get("end_line", mm["line"]) - mm["line"] + 1) if "body" in mm else 0
                node(fid, "fn", mname, "%s.%s" % (c["name"], mname), mm["file"], mm["line"], mm.get("end_line", mm["line"]),
                     h=_h([_norm_code(x.get("body", "")) for x in ms], [sorted(x["params"].items()) for x in ms], mm.get("annos", "")),
                     cls=cid, layer=layer, comment=mm.get("comment", ""), lines=body_lines, overloads=len(ms) if len(ms) > 1 else None,
                     abstract=True if mm.get("abstract") else None, texts=_cjk_literals(mm.get("body", "")),
                     bkey=re.split(r"[_\-.]", mm["file"].rsplit("/", 1)[-1])[0].lower() if c.get("kind") == "package" else None)
                edge(cid, fid, "contains")

    # per-method direct facts: calls, table access, rules, effects
    table_sql = defaultdict(list)
    for cname, cs in idx["classes"].items():
        c = cs[0]
        for mname in c["methods"]:
            t = fb.trace(c["name"], mname, max_depth=0)
            if not t["nodes"]:
                continue
            by_id = {n["id"]: n for n in t["nodes"]}
            root_key = by_id[t["root"]]["key"] if t.get("root") else None
            if not root_key:
                continue
            src = "fn:" + root_key
            for e in t["edges"]:
                a, b = by_id[e["from"]], by_id[e["to"]]
                if b["layer"] == "table":
                    tid = "tbl:" + b["label"].rstrip("()")
                    node(tid, "tbl", b["label"].rstrip("()"), b["label"], kind_="procedure" if b["key"].startswith("P:") else "table")
                    edge("fn:" + a["key"], tid, "writes" if e.get("op") in ("C", "U", "D", "P") else "reads", e.get("op", "R"))
                else:
                    if b["key"].count(".") == 1 and ("fn:" + b["key"]) not in nodes:  # MyBatis statement without Java body
                        node("fn:" + b["key"], "fn", b["key"].split(".")[-1], b["key"], b["file"], b["line"], layer="dao", mapper=True)
                    edge("fn:" + a["key"], "fn:" + b["key"], "calls", file=a.get("file", ""), line=0)
            for op in t["data_ops"]:
                table_sql[op["table"]].append([op["via"], op["op"], op["sql"]])
            n = nodes.get(src)
            if n is not None:
                if t["rules"]:
                    n["data"]["rules"] = [{"if": r["condition"], "msg": r["message"] or r["exception"], "line": r["line"]} for r in t["rules"]][:12]
                for se in t["side_effects"]:
                    xid = "ext:" + se["kind"]
                    node(xid, "ext", se["kind"])
                    edge(src, xid, "effect", file=se["file"], line=se["line"])
                if t["transactions"]:
                    n["data"]["tx"] = True
                if t["unresolved"]:
                    n["data"]["unresolved"] = [u["call"] for u in t["unresolved"]][:8]

    # MyBatis statements: the SQL lives in XML, so it is part of the method's fingerprint
    for (ns, sid), info in fb.mybatis_sql.items():
        fid = "fn:%s.%s" % (ns.split(".")[-1], sid)
        n = nodes.get(fid)
        if n is not None:
            n["hash"] = _h(n["hash"], _norm_code(info["sql"]))
            n["data"].update({"sql": info["sql"][:600], "sql_at": "%s:%d" % (info["file"], info["line"])})

    # tables: DDL + SQL fingerprint
    ddl = {}
    for o in m["db_objects"]:
        ddl.setdefault(o["name"], o)
    for e in m["entities"]:
        tid = "tbl:" + e["table"]
        node(tid, "tbl", e["table"], e["table"], kind_="table", entity=e["class"].split(".")[-1], entity_file=e["file"])
    for t in list(m["tables"]) + list(ddl):
        node("tbl:" + t, "tbl", t, t, kind_="table")
    for nid, n in nodes.items():
        if n["kind"] != "tbl":
            continue
        o = ddl.get(n["name"])
        text = ""
        if o:
            n["file"], n["line"] = o["file"], o["line"]
            text = _ddl_text(root / o["file"], o["line"])
            n["data"]["ddl"] = text[:1500]
            n["data"]["db_kind"] = o["kind"]
        n["data"]["files"] = m["tables"].get(n["name"], [])[:20]
        n["hash"] = _h(_norm_code(text), sorted({(v, o) for v, o, _ in table_sql.get(n["name"], [])}))

    # entries
    for f in flows:
        epid = "ep:" + f["trigger"]
        node(epid, "ep", f["trigger"], f["trigger"], f["file"], f["line"], h=_h(f["trigger"], f["handler"]), entry_kind=f["kind"], handler=f["handler"],
             scope=f.get("scope"), limitations=f.get("limitations"), registration=f.get("registration"))
        edge(epid, "fn:" + f["handler"], "handles")

    # flows
    for f in flows:
        fid = "flow:" + f["id"]
        steps = ["fn:" + n["key"] for n in f["nodes"] if n["layer"] != "table"]
        tabs = sorted(f["crud"])
        node(fid, "flow", f["name"] or f["trigger"], f["name"] or f["trigger"], f["file"], f["line"], trigger=f["trigger"], entry_kind=f["kind"],
             handler=f["handler"], crud=f["crud"], rules=len(f["rules"]), states=len(f["states"]), effects=sorted({s["kind"] for s in f["side_effects"]}),
             unresolved=len(f["unresolved"]), steps=len(steps), scope=f.get("scope"), limitations=f.get("limitations"),
             registration=f.get("registration"))
        edge(fid, "ep:" + f["trigger"], "entry")
        for s in steps:
            edge(fid, s, "step")
        for t, ops in f["crud"].items():
            edge(fid, "tbl:" + t, "uses", ops)
        nodes[fid]["hash"] = _h(f["trigger"], sorted(nodes[s]["hash"] for s in steps if s in nodes), f["crud"])
        flow_keys.add(fid)
    for sm in fdata["state_machines"]:
        sid = "sm:%s.%s" % (sm["table"], sm["column"])
        node(sid, "sm", "%s.%s" % (sm["table"], sm["column"]), h=_h(sm["transitions"]), states=sm["states"],
             transitions=[{"from": t["from"], "to": t["to"], "flow": t["flow"]} for t in sm["transitions"]])
        for fl in {t["flow"] for t in sm["transitions"]}:
            edge("flow:" + fl, sid, "transition")
        if "tbl:" + sm["table"] in nodes:
            edge("tbl:" + sm["table"], sid, "has_state")

    # fan-in / fan-out for code health
    fan_in, fan_out = Counter(), Counter()
    for s, d, k, *_ in edges:
        if k == "calls":
            fan_out[s] += 1
            fan_in[d] += 1
    for nid, n in nodes.items():
        if n["kind"] == "fn":
            if fan_in[nid]:
                n["data"]["fan_in"] = fan_in[nid]
            if fan_out[nid]:
                n["data"]["fan_out"] = fan_out[nid]
        if n["file"] and "file:" + n["file"] in nodes:
            n["module"] = nodes["file:" + n["file"]]["module"]

    # module dependencies (class-level calls across modules)
    mdeps = Counter()
    for s, d, k, *_ in edges:
        if k == "calls" and s in nodes and d in nodes:
            a, b = nodes[s]["module"], nodes[d]["module"]
            if a and b and a != b:
                mdeps[(a, b)] += 1
    for (a, b), c in mdeps.items():
        edge("mod:" + a, "mod:" + b, "depends", str(c))

    # domains (sticky assignment persisted in .tmh/knowledge/domains.json)
    dres = dommod.assign(root, flows, nodes, common)
    for did, d in dres["domains"].items():
        node("dom:" + did, "dom", d["title"], d["title"], h=_h(sorted(d["flows"]), sorted(d["tables"])), key=d.get("key", ""))
        for fl in d["flows"]:
            if "flow:" + fl in nodes:
                nodes["flow:" + fl]["domain"] = did
                edge("flow:" + fl, "dom:" + did, "in")
        for t in d["tables"]:
            if "tbl:" + t in nodes:
                nodes["tbl:" + t]["domain"] = did
                edge("tbl:" + t, "dom:" + did, "in")
    for nid, did in dres["code_domain"].items():
        if nid in nodes:
            nodes[nid]["domain"] = did

    for mid, n in nodes.items():
        if n["kind"] == "mod":
            d = mid[4:]
            mfiles = [x for x in nodes.values() if x["kind"] == "file" and x["module"] == d]
            n["data"].update({"files": len(mfiles), "tests": sum(1 for x in mfiles if x["data"].get("test"))})
            n["hash"] = _h(sorted(x["id"] for x in mfiles), sorted(k for k in mdeps if d in k))

    diagnostics = idx.get("diagnostics", [])
    python_files = [f for f in files if f.endswith(".py")]
    failed_python = sorted({d["file"] for d in diagnostics})
    analysis = {"python": {"files": len(python_files), "parsed": len(python_files) - len(failed_python),
                           "unknown": failed_python}, "diagnostics": diagnostics}
    _write_db(root, nodes, edges, {"flows": len(flows), "analysis": analysis, **stats})
    x = tmh_dir(root)
    (x / "map.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    (x / "flows.json").write_text(json.dumps(fdata, ensure_ascii=False), encoding="utf-8")
    cnt = Counter(n["kind"] for n in nodes.values())
    return {"nodes": len(nodes), "edges": len(edges), "kinds": dict(cnt), "domains": len(dres["domains"]), **stats,
            "map": m, "flows": fdata, "diagnostics": diagnostics, "analysis": analysis}


def _common_package(fqns: list[str]) -> list[str]:
    pk = [f.split(".")[:-1] for f in fqns if "." in f]
    if not pk:
        return []
    pre = pk[0]
    for p in pk[1:]:
        k = 0
        while k < len(pre) and k < len(p) and pre[k] == p[k]:
            k += 1
        pre = pre[:k]
    return pre


def _ddl_text(p: Path, line: int) -> str:
    text = read_text(p) or ""
    lines = text.splitlines()[max(0, line - 1):]
    out = []
    for l in lines[:120]:
        out.append(l)
        if l.rstrip().endswith(";") or l.strip() == "/" or l.strip().upper() == "GO":
            break
    return "\n".join(out)


_CJK_LIT = re.compile(r"\"((?:[^\"\\\n]|\\.)*[\u4e00-\u9fff](?:[^\"\\\n]|\\.)*)\"")


def _cjk_literals(body: str, limit: int = 12) -> list:
    """Chinese string literals in a method (messages, labels, log text): the business words a requirement uses."""
    out = []
    for m in _CJK_LIT.finditer(body or ""):
        t = m.group(1).strip()
        if t and t not in out:
            out.append(t[:80])
        if len(out) >= limit:
            break
    return out or None


def _write_db(root: Path, nodes: dict, edges: list, meta: dict) -> None:
    p = graph_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    if tmp.exists():
        try:
            tmp.unlink()
        except OSError:
            tmp.write_bytes(b"")
    db = open_db(tmp)
    db.executescript("""
    CREATE TABLE nodes(id TEXT PRIMARY KEY, kind TEXT, name TEXT, label TEXT, file TEXT, line INT, end_line INT,
                       domain TEXT, module TEXT, hash TEXT, data TEXT);
    CREATE TABLE edges(src TEXT, dst TEXT, kind TEXT, op TEXT, file TEXT, line INT);
    CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
    """)
    db.executemany("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   [(n["id"], n["kind"], n["name"], n["label"], n["file"], n["line"], n["end"], n["domain"], n["module"], n["hash"],
                     json.dumps(n["data"], ensure_ascii=False)) for n in nodes.values()])
    db.executemany("INSERT INTO edges VALUES(?,?,?,?,?,?)", list(dict.fromkeys(edges)))
    db.executescript("CREATE INDEX e_src ON edges(src); CREATE INDEX e_dst ON edges(dst); CREATE INDEX n_kind ON nodes(kind);")
    db.executemany("INSERT INTO meta VALUES(?,?)", [(k, json.dumps(v)) for k, v in meta.items()])
    db.commit()
    db.close()
    replace_file(tmp, p)


# ---- reading -------------------------------------------------------------
class Graph:
    """Read-only access to graph.db."""

    def __init__(self, root: Path):
        p = graph_path(root)
        if not p.exists():
            raise FileNotFoundError("还没有知识图谱，先运行 tmh kb build")
        self.db = open_db(p)
        self.db.row_factory = sqlite3.Row

    def __del__(self):
        try:
            self.db.close()
        except Exception:
            pass

    def _node(self, r) -> dict:
        d = dict(r)
        d["data"] = json.loads(d["data"] or "{}")
        return d

    def node(self, nid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
        return self._node(r) if r else None

    def nodes(self, kind: str | None = None) -> list[dict]:
        q = "SELECT * FROM nodes" + (" WHERE kind=?" if kind else "")
        return [self._node(r) for r in self.db.execute(q, (kind,) if kind else ())]

    def out(self, nid: str, kind: str | None = None) -> list[dict]:
        q = "SELECT * FROM edges WHERE src=?" + (" AND kind=?" if kind else "")
        return [dict(r) for r in self.db.execute(q, (nid, kind) if kind else (nid,))]

    def inn(self, nid: str, kind: str | None = None) -> list[dict]:
        q = "SELECT * FROM edges WHERE dst=?" + (" AND kind=?" if kind else "")
        return [dict(r) for r in self.db.execute(q, (nid, kind) if kind else (nid,))]

    def hashes(self) -> dict:
        return {r[0]: r[1] for r in self.db.execute("SELECT id, hash FROM nodes")}

    def meta(self) -> dict:
        return {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT k, v FROM meta")}

    def find(self, text: str, limit: int = 20) -> list[dict]:
        like = "%" + text + "%"
        rows = self.db.execute("SELECT * FROM nodes WHERE id=? OR name LIKE ? OR label LIKE ? LIMIT ?", (text, like, like, limit * 3))
        res = [self._node(r) for r in rows]
        order = {"flow": 0, "dom": 1, "tbl": 2, "ep": 3, "cls": 4, "fn": 5, "sm": 6, "mod": 7, "file": 8, "ext": 9}
        res.sort(key=lambda n: (n["id"] != text, n["name"].lower() != text.lower(), order.get(n["kind"], 9)))
        return res[:limit]
